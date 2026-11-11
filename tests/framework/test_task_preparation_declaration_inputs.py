"""Physical producer reads and real downstream consumers, with unit transport edges.

These assertions count actual EvidenceStore calls, not branch labels or counters.
The source/model/kernel/site edges are synthetic; this is no production timing.
"""

from collections import Counter
from dataclasses import replace
import inspect
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.sites.task_preparation_inputs import (
    TaskPreparationDeclarationInputs,
)
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OperationStopped,
    OwnershipConflict,
)
from evidence_control_fixtures import EvidenceFixtureStore
from site_instance_fixtures import node_path as node_path
from task_actor_input_fixtures import fixed_task_source_inputs
from task_resource_owner_fixtures import owned_task


def test_original_producer_reads_once_and_consumers_do_not_reload(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, r):
        fixed = fixed_task_source_inputs(c, r, monkeypatch)
        assert r.inputs is not None
        held = r.inputs.preparation_declarations
        assert isinstance(held, TaskPreparationDeclarationInputs)
        refs = {
            c.p.plan.declaration_ref,
            c.p.declaration.site_spec_ref,
            c.p.plan.reset_plan_ref,
            c.p.declaration.task_binding_ref,
        }
        reads: Counter[Any] = Counter()
        original = EvidenceFixtureStore.read

        def read(self: Any, reference: Any, control: Any = None) -> bytes:
            if reference in refs and c.native.loader.session.calls == 0:
                frames = inspect.stack(context=0)
                logical = [
                    f
                    for f in frames
                    if "/src/lab_generate_skill/" in f.filename
                    and Path(f.filename).name
                    not in {"state_reads.py", "task_preparation_evidence.py"}
                    and not (
                        Path(f.filename).name == "context_evidence.py"
                        and f.function == "read_bytes"
                    )
                ]
                assert logical
                leaf = (Path(logical[0].filename).name, logical[0].function)
                if leaf == ("task_preparation.py", "_declared"):
                    reads[reference] += 1
                    assert reads[reference] == 1, (reference, leaf)
                elif (
                    leaf[0] == "task_native_authority.py"
                    or leaf == ("task_preparation_admission.py", "proof")
                    or (
                        leaf == ("task_state_admission.py", "verify")
                        and any(
                            Path(f.filename).name == "task_preparation_admission.py"
                            for f in logical
                        )
                    )
                    or leaf == ("task_initialization.py", "start")
                ):
                    pytest.fail(
                        f"Direct reused declaration body physically reread: {reference}; {[(Path(f.filename).name,f.function) for f in logical]}"
                    )
                # A distinct context/baseline/readback reader still verifies its
                # own first complete graph. The nearest reader identifies it;
                # outer initializer frames do not turn it into a direct read.
            return original(self, reference, control)

        monkeypatch.setattr(EvidenceFixtureStore, "read", read)
        result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
        assert result.evaluation.status == "success"
        assert set(reads) == refs and set(reads.values()) == {1}
        assert held.statistics["declaration_graph_reads"] == 1
        assert held.statistics["declaration_integrity_checks"] == 1
        assert held.statistics["declaration_graph_reuses"] > 5
        assert fixed.current_calls > held.statistics["declaration_graph_reuses"]
        assert c.native.loader.session.calls == 1
        assert c.bundle.finalization.state.reset is not None
        assert c.bundle.finalization.state.reset.status == "safe"
        assert not r.inputs.active and r.inputs.preparation_declarations is None
        assert held.facts is None
        with pytest.raises(OwnershipConflict):
            held.require(
                c.p.plan,
                c.p.declaration,
                c.p.plan.operation,
                c.p.original.resource.controls.bind(c.p.plan.operation),
            )


@pytest.mark.parametrize("fault", ["body", "missing", "storage", "cancel"])
def test_carried_declarations_refuse_changes_before_effects_and_keep_cleanup(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, r):
        fixed = fixed_task_source_inputs(c, r, monkeypatch)
        assert r.inputs is not None
        held = r.inputs.preparation_declarations
        assert isinstance(held, TaskPreparationDeclarationInputs)
        original = held.require
        injected = False

        def require(*args: Any, **kwargs: Any) -> Any:
            nonlocal injected
            if not injected and c.bundle.preparation.state.phase == "preparing":
                injected = True
                assert held.facts is not None
                if fault == "body":
                    held.facts = replace(
                        held.facts,
                        binding=held.facts.binding.model_copy(
                            update={
                                "private_spec_ref": held.facts.binding.private_spec_ref.model_copy(
                                    update={"producer": "changed-body"}
                                )
                            }
                        ),
                    )
                elif fault == "missing":
                    held.clear()
                elif fault == "storage":
                    fixed.denied = True
                else:
                    raise OperationStopped("CANCELLED", c.p.plan.operation.operation_id)
            return original(*args, **kwargs)

        monkeypatch.setattr(held, "require", require)
        with pytest.raises(TaskExecutionUnconfirmed) as failed:
            c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
        assert injected and failed.value.primary is not None
        chain: list[BaseException] = []
        error: BaseException | None = failed.value.primary
        while error is not None and len(chain) < 16:
            chain.append(error)
            error = getattr(error, "primary", None) or error.__cause__
        expected = (
            EvidenceIntegrityError
            if fault == "body"
            else OperationStopped if fault == "cancel" else OwnershipConflict
        )
        assert any(isinstance(error, expected) for error in chain), chain
        assert c.native.loader.session.calls == 0
        assert held.statistics["declaration_graph_reads"] == 1
        assert c.bundle.preparation.state.references
        assert held.facts is None and not r.inputs.active
        assert r.inputs.preparation_declarations is None


def test_missing_foreign_and_duplicate_declarations_never_rebuild(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, r):
        fixed_task_source_inputs(c, r, monkeypatch)
        assert r.inputs is not None
        held = r.inputs.preparation_declarations
        assert isinstance(held, TaskPreparationDeclarationInputs)
        plan, op = c.p.plan, c.p.plan.operation
        control = c.p.original.resource.controls.bind(op)
        with r.inputs.scope():
            with pytest.raises(OwnershipConflict, match="no consumer rebuild"):
                held.require(plan, c.p.declaration, op, control)
            c.bundle.preparation._declared(control, op)
            assert held.facts is not None
            for field in ("producer", "visibility", "media_type"):
                ref = plan.declaration_ref.model_copy(update={field: "foreign"})
                with pytest.raises(OwnershipConflict):
                    held.require(
                        plan.model_copy(update={"declaration_ref": ref}),
                        c.p.declaration,
                        op,
                        control,
                    )
            original_spec = c.bundle.preparation.spec
            c.bundle.preparation.spec = original_spec.model_copy(
                update={
                    "configuration": original_spec.configuration.model_copy(
                        update={
                            "token": original_spec.token.model_copy(
                                update={"allocation_id": "foreign-spec"}
                            )
                        }
                    )
                }
            )
            with pytest.raises(OwnershipConflict, match="original live site"):
                c.bundle.preparation._declared(control, op)
            c.bundle.preparation.spec = original_spec
            with pytest.raises(OwnershipConflict, match="already retained"):
                held.record(plan, held.facts, op, control)
        assert held.statistics["declaration_graph_reads"] == 1
        assert not c.p.requests and c.native.loader.session.calls == 0
