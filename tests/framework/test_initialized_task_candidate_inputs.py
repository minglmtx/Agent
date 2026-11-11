"""Late candidate read uses actual completed preparation/unique0/baseline facts."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.sites.task_initialization import (
    RecordedTaskInitialization,
)
from lab_generate_skill.bootstrap.task_initialization import DeferredTaskInitialization
from lab_generate_skill.bootstrap.task_candidate_inputs import (
    InitializedTaskCandidateInputs,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from site_instance_fixtures import node_path as node_path
from task_capture_port_fixtures import capture_case


def test_candidate_reader_uses_only_actual_complete_initialization_and_readonly_repeat(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with capture_case(node_path, monkeypatch) as case:
        p, i = case.initial.preparation, case.initial
        calls = []

        def factory(
            plan: TaskExecutionPlan, op: OperationContext, control: OperationControl
        ) -> RecordedTaskInitialization:
            control.checkpoint()
            assert (
                p.preparation.state.result_ref
                == i.initialization.declaration.prepared_result_ref
            )
            calls.append(op)
            return i.initialization

        late = DeferredTaskInitialization(p.plan, factory)
        reader = InitializedTaskCandidateInputs(
            late, p.original.resource.evidence, p.original.resource.controls
        )
        expected = i.initialization.declaration
        with pytest.raises(OwnershipConflict):
            reader.load(
                expected.prepared_result_ref, p.plan.skill_ref, p.plan.operation
            )
        assert calls == [] and i.backend.engines == []
        op = p.plan.operation.model_copy(
            update={"operation_id": p.plan.operation.operation_id + ".starting"}
        )
        result = late.start(p.plan, op, p.original.resource.controls.bind(op))
        first = reader.load(result.equivalence_ref, p.plan.skill_ref, p.plan.operation)
        assert first.baseline.scope == result.actor.scope
        assert (
            first.skill == result.actor.skill
            and first.context.task == result.actor.task
        )
        assert first.observation.record.sequence == 0
        assert first.baseline.observation_ref == result.actor.initial_observation_ref
        before = list(i.backend.calls)
        assert (
            reader.load(result.equivalence_ref, p.plan.skill_ref, p.plan.operation)
            == first
        )
        assert i.backend.calls == before and len(calls) == 1
        for eq, skill in [
            (p.plan.reset_plan_ref, p.plan.skill_ref),
            (result.equivalence_ref, expected.prepared_result_ref),
        ]:
            with pytest.raises(OwnershipConflict):
                reader.load(eq, skill, p.plan.operation)
        with monkeypatch.context() as patch:
            patch.setattr(i.initialization.state, "phase", "quarantined")
            with pytest.raises(OwnershipConflict):
                reader.load(result.equivalence_ref, p.plan.skill_ref, p.plan.operation)
        assert i.backend.calls == before
