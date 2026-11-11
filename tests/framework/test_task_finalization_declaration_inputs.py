"""Original owned constructors through Actor and cleanup declaration consumers."""

from collections import Counter
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.sites.task_finalization_authority import (
    OriginalTaskFinalizationAuthority,
)
from lab_generate_skill.application.actor_context_review import (
    RecordedActorContextInputs,
)
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.application.task_finalization_admission import (
    TaskFinalizationAuthority as CleanupAdmission,
)
from lab_generate_skill.adapters.sites.task_finalization import (
    TaskFinalizationUnconfirmed,
)
from lab_generate_skill.domain.errors import OperationStopped, OwnershipConflict
from site_instance_fixtures import node_path as node_path
from task_resource_owner_fixtures import owned_task
from task_actor_input_fixtures import fixed_task_source_inputs


@pytest.mark.parametrize(
    "fault", ["none", "actor", "body", "reference", "storage", "cancel"]
)
def test_owned_cleanup_reuses_only_exact_declarations_and_keeps_live_gates(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, r):
        fixed = fixed_task_source_inputs(c, r, monkeypatch)
        original = OriginalTaskFinalizationAuthority.read_finalization_declaration
        calls = 0
        misses: Counter[Any] = Counter()
        retained: list[dict[Any, bytes]] = []
        injected = False
        last_context: list[Any] = []
        seen_refs: list[Any] = []

        def read(
            self: Any, plan: Any, declaration: Any, ref: Any, op: Any, control: Any
        ) -> bytes:
            nonlocal calls, injected
            calls += 1
            last_context[:] = [op, control]
            seen_refs.append(ref)
            held = r.inputs
            assert held is not None and held.active
            saved = held.finalization_declarations
            bodies = {} if saved is None else saved[1]
            if calls == 2 and fault in ("body", "reference", "storage", "cancel"):
                injected = True
                assert bodies
                if fault == "body":
                    first = next(iter(bodies))
                    bodies[first] += b" "
                    ref = first
                elif fault == "reference":
                    ref = ref.model_copy(update={"producer": "changed-producer"})
                elif fault == "storage":
                    fixed.denied = True
                else:
                    raise OperationStopped("CANCELLED", op.operation_id)
            if ref not in bodies:
                misses[ref] += 1
            result = original(self, plan, declaration, ref, op, control)
            assert held.finalization_declarations is not None
            values = held.finalization_declarations[1]
            if not retained:
                retained.append(values)
            return result

        monkeypatch.setattr(
            OriginalTaskFinalizationAuthority, "read_finalization_declaration", read
        )
        if fault == "actor":

            def stopped(*args: Any, **kwargs: Any) -> Any:
                raise OperationStopped("DEADLINE_EXCEEDED", "original-actor")

            monkeypatch.setattr(RecordedActorContextInputs, "verify", stopped)
        if fault == "none":
            result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert result.evaluation.status == "success"
        else:
            with pytest.raises(TaskExecutionUnconfirmed) as failed:
                c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            if fault == "actor":
                assert failed.value.primary is not None
            else:
                assert injected and failed.value.cleanup_errors
        if fault in ("none", "actor"):
            assert c.bundle.finalization.state.reset is not None
            assert c.bundle.finalization.state.reset.status == "safe"
            assert len(misses) == 5 and max(misses.values()) == 1
            assert calls > 5
        elif fault in ("reference", "cancel"):
            # The fault is one read after confirmed physical close. Original
            # restoring admission may recheck and restore once; the error must
            # remain unconfirmed even when that independent cleanup succeeds.
            first_error = failed.value.cleanup_errors[0]
            assert isinstance(first_error, TaskFinalizationUnconfirmed)
            assert isinstance(
                first_error.primary,
                OwnershipConflict if fault == "reference" else OperationStopped,
            )
            assert first_error.failed_phase == "close-admission"
            assert first_error.known_closed is not None
            assert c.bundle.finalization.state.reset is not None
            assert c.bundle.finalization.state.reset.status == "safe"
            assert [request.action for request in c.p.requests].count("restore") == 1
        else:
            assert c.bundle.finalization.state.reset is None
        assert r.inputs is not None and not r.inputs.active
        assert r.inputs.finalization_declarations is None
        assert retained
        # A reference and even a still-held dictionary do not extend the task.
        assert all(not values for values in retained)
        op, control = last_context
        admission = c.bundle.finalization.authority
        assert isinstance(admission, CleanupAdmission)
        source = admission.source
        assert isinstance(source, OriginalTaskFinalizationAuthority)
        with pytest.raises(OwnershipConflict):
            original(
                source,
                c.p.plan,
                c.bundle.finalization.declaration,
                seen_refs[0],
                op,
                control,
            )
