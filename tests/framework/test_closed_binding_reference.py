"""Exact task-reference reads in the existing fixed source proof worker.

Actual installation reads retained4901844 evidence only. No source/Actor replay,
old-owner regrant or current production source qualification is inferred.
"""

import json
import os
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadFailure,
)
from lab_generate_skill.adapters.plans.closed_source_protocol import (
    decode_command,
    ClosedSourceReadReply,
)
from lab_generate_skill.adapters.storage.readonly_evidence import ReadOnlyEvidence
from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.domain.closed_source_read import ClosedSourceReadCommand
from lab_generate_skill.domain.evidence_read_scope import EvidenceReadScope
from lab_generate_skill.domain.execution_task_source import ExecutionTaskInputs
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.run_plan import ExecutionWorkload
from lab_generate_skill.ports.lifecycle import OperationControl
from closed_source_read_fixtures import actual_read_case
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from test_closed_plan_inputs import retained_plan
from test_closed_source_read_protocol import E, original_material
from test_slurm_commands import guard
from registered_storage_fixtures import request
from task_binding_fixtures import fixture
from test_run_journal import command


def test_actual_installed_reference_reads_full_original_binding_repeat_and_missing(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    material, root, plan = retained_plan()
    raw = ReadOnlyEvidence(root, max_object_bytes=64 * 1024**2)
    assert isinstance(plan.workload, ExecutionWorkload)
    inputs = ExecutionTaskInputs.model_validate_json(
        raw.read(plan.workload.task_inputs_ref, guard(30))
    )
    ref = inputs.task_binding_ref
    c = actual_read_case(tmp_path, installed_sources, retained=(material, root))
    before = {p.name: p.read_bytes() for p in (tmp_path / "sessions").iterdir()}
    body_counts = []
    for _ in range(2):
        context = c.transport.read(material, guard(60), binding_reference=ref)
        reply = c.transport.last_reply
        assert reply is not None and reply.binding == plan.tasks[0]
        assert reply.binding_reference == ref
        assert reply.schema_version == "closed-source-read-reply/2"
        assert reply.binding_bodies is not None
        obtained = reply.binding_bodies.inputs()
        assert obtained.binding == plan.tasks[0]
        assert obtained.public_task.identity == obtained.binding.identity
        assert obtained.private_spec == raw.read(
            obtained.binding.private_spec_ref, guard(30)
        )
        assert obtained.baseline == raw.read(obtained.binding.baseline_ref, guard(30))
        invalid_version = reply.model_dump(mode="json")
        invalid_version["schema_version"] = "closed-source-read-reply/1"
        with pytest.raises(ValueError, match="version2"):
            ClosedSourceReadReply.model_validate_json(json.dumps(invalid_version))
        missing_bodies = reply.model_dump(mode="json")
        missing_bodies.pop("binding_bodies")
        with pytest.raises(ValueError, match="Version2"):
            ClosedSourceReadReply.model_validate_json(json.dumps(missing_bodies))
        assert (
            reply.body_read_count is not None
            and 0 < reply.body_read_count < reply.read_count
        )
        body_counts.append(
            {
                "logical": reply.read_count,
                "physical_completed": reply.body_read_count,
                "unique_objects": reply.unique_objects,
            }
        )
        assert reply.context == context and reply.read_count > reply.unique_objects > 4
        assert c.transport.last_request is not None
        assert decode_command(c.transport.last_request).binding_reference == ref
    missing = ref.model_copy(
        update={"uri": "cas://sha256/" + "0" * 64, "sha256": "0" * 64}
    )
    with pytest.raises(ClosedSourceReadFailure):
        c.transport.read(material, guard(60), binding_reference=missing)
    assert c.transport.last_reply is not None
    assert (
        c.transport.last_reply.binding is None
        and c.transport.last_reply.binding_reference is None
    )
    assert c.current.store.state == "ready" and not c.transport.quarantined
    with pytest.raises(OwnershipConflict):
        c.transport.require_current(material, c.op)
    assert before == {p.name: p.read_bytes() for p in (tmp_path / "sessions").iterdir()}
    (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
        / "closed-binding-reference-actual.json"
    ).write_text(
        json.dumps(
            {
                "historical_job": 4901844,
                "scope": "retained readonly full source and original task-binding dependencies/semantic algorithm; no current grant/Actor/replay",
                "timings": c.transport.timings,
                "body_counts": body_counts,
                "old_namespace_written": False,
            },
            indent=2,
        )
        + "\n"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "binding_reference"},
        {"kind": "binding_reference", "binding_reference": None},
        {"binding_reference": None},
        {"kind": "binding_reference", "binding_reference": {}},
        {"kind": "binding_reference", "binding_reference": []},
        {"kind": "binding_reference", "binding_reference": "wrong"},
    ],
)
def test_reference_request_missing_wrong_type_or_other_kind_rejected(
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


def test_optional_loader_is_per_call_without_parent_leaf_transport_or_permission_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = fixture(tmp_path)
    ref = d.records.publish(d.binding, command())
    calls = []

    class Checks:
        def load_binding(
            self,
            reference: EvidenceRef,
            op: OperationContext,
            control: OperationControl,
        ) -> TaskBinding:
            calls.append(reference)
            control.checkpoint()
            return d.records.load(reference, op)

    records = EvidenceTaskBindings(
        d.store, d.controls, d.authority, load_checks=Checks()
    )

    def forbidden(*a: Any, **k: Any) -> Any:
        pytest.fail("delegated load repeated parent leaf reads")

    monkeypatch.setattr(records.reader, "load", forbidden)
    assert records.load(ref, command()) == records.load(ref, command()) == d.binding
    assert calls == [ref, ref]
    d.authority.denied = True
    with pytest.raises(OwnershipConflict):
        records.load(ref, command())
    assert calls == [ref, ref, ref]
    with pytest.raises(ValueError):
        records.load(d.binding.public_task_ref, command())
    assert calls == [ref, ref, ref]
