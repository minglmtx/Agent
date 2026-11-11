"""Full immutable source in one installed proof; live claim never cached.

The actual case reads retained failed 4904699 only. It cannot grant its old
owner new work, replay its claim or start a website/model.
"""

import json
import os
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.plans.execution_task_source import (
    OriginalExecutionTaskSource,
)
from lab_generate_skill.adapters.plans.closed_source_protocol import decode_command
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadFailure,
)
from lab_generate_skill.domain.closed_source_read import (
    ClosedMapReadMaterial,
    ClosedSourceReadCommand,
)
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence_read_scope import EvidenceReadScope
from lab_generate_skill.domain.execution_task_source import ExecutionSourceFacts
from lab_generate_skill.ports.lifecycle import OperationControl
from execution_task_phase_fixtures import phase_case
from closed_source_read_fixtures import actual_read_case
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from test_closed_source_read_protocol import E, original_material
from test_slurm_commands import guard
from registered_storage_fixtures import request


def test_actual_installed_single_source_proof_repeat_missing_and_original_scope(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    root = E / "production-4904699"
    material = ClosedMapReadMaterial.model_validate_json(
        (root / "source-read/closed-declarations.json").read_bytes()
    )
    plan = TaskExecutionPlan.model_validate_json(
        (
            root
            / "evidence/blobs/8f264141d58c2342ba90e00f8c72a95995e9891d230188ef26a7afe2d6c21e78"
        ).read_bytes()
    )
    c = actual_read_case(
        tmp_path, installed_sources, retained=(material, root / "evidence")
    )
    before = {p.name: p.read_bytes() for p in (tmp_path / "sessions").iterdir()}
    counts = []
    first = None
    for _ in range(2):
        context = c.transport.read(material, guard(60), execution_plan=plan)
        reply = c.transport.last_reply
        assert reply is not None and reply.execution_source is not None
        assert reply.schema_version == "closed-source-read-reply/6"
        assert reply.execution_claim is not None
        assert reply.execution_claim.reference == plan.intent.binding.claim_ref
        with pytest.raises(ValueError):
            type(reply).model_validate(
                reply.model_copy(update={"execution_claim": None})
            )
        with pytest.raises(ValueError):
            type(reply).model_validate(
                reply.model_copy(
                    update={"schema_version": "closed-source-read-reply/1"}
                )
            )
        facts = reply.execution_source
        assert facts.source.intent == plan.intent
        assert facts.context == context and facts.source.run == plan.intent.binding.run
        assert facts.inputs.task_binding_ref == plan.evaluation.task_contract_ref
        assert first is None or first == facts
        first = facts
        assert (
            reply.body_read_count is not None
            and 0 < reply.body_read_count < reply.read_count
        )
        counts.append((reply.read_count, reply.body_read_count, reply.unique_objects))
        assert c.transport.last_request is not None
        assert decode_command(c.transport.last_request).execution_plan == plan
    assert plan.source_ref is not None
    missing = plan.source_ref.model_copy(
        update={"uri": "cas://sha256/" + "0" * 64, "sha256": "0" * 64}
    )
    with pytest.raises(ClosedSourceReadFailure):
        c.transport.read(
            material,
            guard(60),
            execution_plan=plan.model_copy(update={"source_ref": missing}),
        )
    assert (
        c.transport.last_reply is not None
        and c.transport.last_reply.execution_source is None
    )
    with pytest.raises(OwnershipConflict):
        c.transport.require_current(material, c.op)
    assert c.current.store.state == "ready" and not c.transport.quarantined
    assert before == {p.name: p.read_bytes() for p in (tmp_path / "sessions").iterdir()}
    (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
        / "closed-execution-source-actual.json"
    ).write_text(
        json.dumps(
            {
                "historical_job": 4904699,
                "scope": "retained immutable source only; no current qualification, durable claim or resource grant",
                "timings": c.transport.timings,
                "logical_physical_unique": counts,
                "old_namespace_written": False,
            },
            indent=2,
        )
        + "\n"
    )


def test_delegated_source_keeps_fresh_durable_claim_and_scope_without_parent_leaf_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = phase_case(tmp_path / "unit-source")
    c = f.task
    original = c.source.source_reader
    op = c.plan.read_operation
    control = c.deps.controls.bind(op)
    facts = original.load(c.plan, op, control)
    calls = []

    class Checks:
        def load_source(
            self,
            plan: TaskExecutionPlan,
            operation: OperationContext,
            control: OperationControl,
        ) -> ExecutionSourceFacts:
            calls.append(plan)
            control.checkpoint()
            return facts

    reader = OriginalExecutionTaskSource(
        original.plans,
        original.claims,
        original.contexts,
        original.bindings,
        original.reads.store,
        source_checks=Checks(),
    )

    def forbidden(*a: Any, **kw: Any) -> Any:
        pytest.fail("delegated source repeated parent immutable leaf reads")

    monkeypatch.setattr(reader.reads, "parse", forbidden)
    for _ in range(2):
        assert reader.load(c.plan, op, control) == facts
    assert len(calls) == 2
    c.source.claim_authority.denied = True
    with pytest.raises(OwnershipConflict):
        reader.load(c.plan, op, control)
    assert len(calls) == 3
    with pytest.raises(OwnershipConflict):
        reader.load(c.plan, c.plan.operation, control)
    assert len(calls) == 3 and not c.phases.calls


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "execution_source"},
        {"kind": "execution_source", "execution_plan": None},
        {"execution_plan": None},
        {"kind": "execution_source", "execution_plan": {}},
        {"kind": "execution_source", "execution_plan": []},
        {"kind": "execution_source", "execution_plan": "wrong"},
    ],
)
def test_source_request_wrong_kind_missing_empty_or_type_before_io(
    tmp_path: Path, change: dict[str, Any]
) -> None:
    material, _ = original_material()
    original = request(tmp_path, create=True)
    scope = EvidenceReadScope(
        binding=original.binding,
        config=original.config,
        controller=original.controller,
        operation=original.operation,
        revision=0,
    )
    values = dict(
        scope=scope, material=material, workspace_root=str(E.parents[1]), kind="context"
    )
    values.update(change)
    with pytest.raises(ValueError):
        ClosedSourceReadCommand.model_validate(values)
