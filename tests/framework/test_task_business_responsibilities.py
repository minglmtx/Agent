"""Business boundaries checked with actual source/claims/journals, unit effects."""

import ast
from pathlib import Path
import pytest
from lab_generate_skill.application.execute_task import execute_task
from lab_generate_skill.application.task_completion import CompletedTaskExecution
from lab_generate_skill.application.construction_task_result import (
    construction_task_result,
)
from lab_generate_skill.application.execution_task_result import execution_task_result
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.task_execution_result import (
    ExecutedTaskReceipt,
    TaskAttemptResult,
)
from task_execution_fixtures import task_case
from execution_task_fixtures import execution_case


def test_common_completion_has_same_shape_without_business_publication(
    tmp_path: Path,
) -> None:
    construction = task_case(tmp_path / "construction")
    single = execution_case(tmp_path / "single")
    first = execute_task(construction.plan, construction.deps)
    second = execute_task(single.plan, single.deps)
    assert type(first) is type(second) is CompletedTaskExecution
    for completed in (first, second):
        assert completed.generations == completed.interactions == 1
        assert completed.facts.schema_version == "task-completion-facts/1"
        assert {"closed", "reset"}.issubset(completed.events.known)
        assert (
            "execution" not in completed.events.known
            and "attempt" not in completed.events.known
        )
    assert not hasattr(single.deps, "construction") and not hasattr(
        single.deps, "admission"
    )
    assert set(single.source.run.request_bounds()) == {"actor"}


@pytest.mark.parametrize("source", ["construction", "execution"])
def test_wrong_business_adapter_refuses_without_publication_or_reexecution(
    tmp_path: Path, source: str
) -> None:
    c = (
        task_case(tmp_path / "case")
        if source == "construction"
        else execution_case(tmp_path / "case")
    )
    completed = execute_task(c.plan, c.deps)
    before = (
        dict(completed.events.known),
        tuple(completed.events.retained),
        list(c.phases.calls),
    )
    with pytest.raises(OwnershipConflict):
        (
            execution_task_result
            if source == "construction"
            else construction_task_result
        )(completed)
    assert before == (
        completed.events.known,
        tuple(completed.events.retained),
        c.phases.calls,
    )
    assert c.model.calls == c.browser.calls == 1


def test_construction_conversion_preserves_exact_historical_envelopes(
    tmp_path: Path,
) -> None:
    c = task_case(tmp_path / "construction")
    completed = execute_task(c.plan, c.deps)
    result = construction_task_result(completed)
    store = c.admission.data.store
    envelope = TaskAttemptResult.model_validate_json(store.read(result.attempt_ref))
    raw = store.read(envelope.execution_ref)
    receipt = ExecutedTaskReceipt.model_validate_json(raw)
    expected = ExecutedTaskReceipt.model_validate(
        {
            **completed.facts.model_dump(exclude={"schema_version"}),
            "schema_version": "executed-task-receipt/1",
        }
    )
    assert receipt == expected and raw == expected.model_dump_json().encode()
    assert envelope.schema_version == "attempt-result/1"
    assert "execution_source_ref" not in c.plan.model_dump_json()
    assert "execution_policy_ref" not in c.plan.intent.model_dump_json()
    assert "source_ref" not in c.plan.model_dump()


def test_common_control_flow_cannot_choose_candidate_teacher_or_business_results() -> (
    None
):
    root = Path(__file__).resolve().parents[2] / "src/lab_generate_skill/application"
    for filename in ("execute_task.py", "task_execution_events.py"):
        tree = ast.parse((root / filename).read_text())
        attributes = {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        assert not attributes.intersection(
            {
                "construction",
                "candidate_slot",
                "pending_attempt",
                "revision_round",
                "source_kind",
            }
        )
        imported = {
            node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        }
        assert not any(
            name
            and name.endswith(
                (
                    ".construction",
                    ".construction_state",
                    ".admit_candidate",
                    ".construction_task_result",
                    ".execution_task_result",
                )
            )
            for name in imported
        )


def test_bootstrap_selects_single_admission_and_business_result_without_construction(
    tmp_path: Path,
) -> None:
    from lab_generate_skill.bootstrap.task_execution_composition import (
        bind_task_execution,
        TaskExecutionServices,
        ExecutionTaskRuntime,
    )
    from lab_generate_skill.bootstrap.execution_task import RecordedExecutionTask
    from lab_generate_skill.application.execution_task_admission import (
        ExecutionTaskAdmission,
    )

    c = execution_case(tmp_path / "single")
    d = c.deps
    services = TaskExecutionServices(
        d.preparation,
        d.initialization,
        d.capture,
        d.evaluator,
        d.finalization,
        d.states,
        d.inputs,
    )
    runtime = ExecutionTaskRuntime(
        d.source_reader, d.runs, d.claims, d.authority, d.evidence, d.controls, d.clock
    )
    task = bind_task_execution(c.plan, services, runtime, d.actors)
    assert isinstance(task, RecordedExecutionTask) and isinstance(
        task.deps.source, ExecutionTaskAdmission
    )
    assert not hasattr(task.deps, "construction")
    result = task.execute(c.plan.intent, c.plan.operation)
    assert result.schema_version == "execution-task-result/1"
    assert result.generations == result.interactions == c.model.calls == 1
    assert c.phases.calls[-3:] == ["close", "verify_closed", "restore"]
    from lab_generate_skill.domain.errors import DispatchAlreadyCommitted

    with pytest.raises(DispatchAlreadyCommitted):
        task.execute(c.plan.intent, c.plan.operation)


def test_single_runtime_cannot_relabel_construction_or_hide_missing_actor_rights(
    tmp_path: Path,
) -> None:
    from lab_generate_skill.bootstrap.task_execution_composition import (
        bind_task_execution,
        TaskExecutionServices,
        ExecutionTaskRuntime,
    )

    c = execution_case(tmp_path / "single")
    other = task_case(tmp_path / "construction")
    d = c.deps
    services = TaskExecutionServices(
        d.preparation,
        d.initialization,
        d.capture,
        d.evaluator,
        d.finalization,
        d.states,
        d.inputs,
    )
    runtime = ExecutionTaskRuntime(
        d.source_reader, d.runs, d.claims, d.authority, d.evidence, d.controls, d.clock
    )
    with pytest.raises(OwnershipConflict):
        bind_task_execution(other.plan, services, runtime, d.actors)
    assert not c.phases.calls and not other.phases.calls


def test_single_lifecycle_can_import_without_construction_admission_or_progress() -> (
    None
):
    import subprocess, sys

    program = """
import sys
from lab_generate_skill.application.execute_task import execute_task
from lab_generate_skill.application.execution_task_deps import ExecutionTaskExecutionDeps
from lab_generate_skill.adapters.plans.execution_task_source import OriginalExecutionTaskSource
for name in ('lab_generate_skill.domain.construction_state',
             'lab_generate_skill.application.admit_candidate',
             'lab_generate_skill.application.construct_targets',
             'lab_generate_skill.ports.construction'):
    assert name not in sys.modules, name
"""
    subprocess.run([sys.executable, "-B", "-c", program], check=True)


@pytest.mark.parametrize("source", ["construction", "execution"])
def test_result_publication_failure_retains_sealed_task_and_no_reexecution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
    from lab_generate_skill.ports.lifecycle import OperationControl
    from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
    from lab_generate_skill.domain.errors import DispatchAlreadyCommitted

    c = (
        task_case(tmp_path / "case")
        if source == "construction"
        else execution_case(tmp_path / "case")
    )
    completed = execute_task(c.plan, c.deps)
    store = c.deps.evidence
    put = store.put
    failure = OSError("original result acknowledgement lost")
    committed: list[EvidenceRef] = []

    def lost(
        data: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        ref = put(data, metadata, control=control)
        if metadata.content_schema.startswith("executed-task-receipt/"):
            committed.append(ref)
            raise failure
        return ref

    monkeypatch.setattr(store, "put", lost)
    with pytest.raises(TaskExecutionUnconfirmed) as caught:
        (
            construction_task_result
            if source == "construction"
            else execution_task_result
        )(completed)
    assert caught.value.primary is failure and caught.value.__cause__ is failure
    assert len(committed) == 1 and "reset" in caught.value.known
    assert c.model.calls == c.browser.calls == 1
    with pytest.raises(DispatchAlreadyCommitted):
        execute_task(c.plan, c.deps)
