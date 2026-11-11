"""Current task Actor gate, original hard budget and no unknown replay."""

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.application.execute_task import (
    execute_task,
    TaskExecutionUnconfirmed,
)
from lab_generate_skill.application.actor_loop import ActorLoopFailure
from lab_generate_skill.application.actor_model_admission import TraceActorAuthority
from lab_generate_skill.bootstrap.actor_runtime import RetainedActorReturns
from lab_generate_skill.domain.local_actor import LocalActorExecution
from lab_generate_skill.application.task_actor_admission import (
    ConstructionTaskActorAuthority,
    TaskActorAdmissionDeps,
)
from lab_generate_skill.bootstrap.actor_runtime import original_actor_runtime
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.actor_admission import PreparedActorInput
from lab_generate_skill.domain.task_execution import InitializedTask, TaskExecutionPlan
from lab_generate_skill.domain.execution import RunEvent, ExecutionFailure
from lab_generate_skill.domain.run_journal import RunEntry
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.adapters.models.actor_count_protocol import (
    decode_worker_command,
)
from lab_generate_skill.domain.trace_events import GenerationPlanned
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.bootstrap.actor_projection import build_actor_projection
from lab_generate_skill.domain.actor_projection import FullAxProjection
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.actor.prompting import prepare_actor
from construction_storage_fixtures import put
from task_actor_v2_fixtures import current_task_case
from test_run_journal import command


@pytest.mark.parametrize(
    "fault",
    [
        "source",
        "claim",
        "stopped",
        "route",
        "parameters",
        "round",
        "legacy",
        "teacher_role",
        "cancel",
    ],
)
def test_new_task_actor_rejects_original_admission_conflicts_before_worker_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    c = current_task_case(tmp_path / fault, monkeypatch)
    task = c.task
    request = task.phases.initialized.actor
    if fault == "source":
        c.source.denied = True
    elif fault == "claim":
        c.source.callback = lambda: setattr(
            task.admission.data.claim_authority, "denied", True
        )
    elif fault == "stopped":

        def stopped() -> None:
            snapshot = task.deps.runs.read(task.plan.read_operation)
            parent = snapshot.project()[0].events[-1].operation.operation_id
            error = ExecutionFailure(
                component_id="controller",
                reason_code="unit-stopped",
                message="Original run stopped during Actor admission",
            )
            entry = RunEntry(
                event=RunEvent(
                    stage="closing",
                    operation=command("current-task-stop", cleanup_parent=parent),
                    previous_operation_id=parent,
                    occurred_at=datetime.now(timezone.utc),
                    component_id="controller",
                    stop_reason="error",
                    primary_error=error,
                    outputs=(
                        put(task.admission.data.store, error, "execution-failure/1"),
                    ),
                )
            )
            task.deps.runs.append(entry, snapshot.revision, entry.event.operation)

        c.source.callback = stopped
    elif fault == "cancel":

        def cancelled() -> None:
            raise OperationStopped("CANCELLED", request.operation.operation_id)

        c.source.callback = cancelled
    elif fault in ("route", "parameters", "teacher_role"):
        assert request.context_configuration_ref is not None
        config = ActorContextConfiguration.model_validate_json(
            task.admission.data.store.read(request.context_configuration_ref)
        )
        if fault == "teacher_role":
            raw = json.loads(config.model_dump_json())
            raw["policy"]["role"] = "teacher"
            raw_ref = task.admission.data.store.put(
                json.dumps(raw).encode(),
                EvidenceMetadata.model_validate(
                    request.context_configuration_ref.model_dump(
                        include={
                            "media_type",
                            "content_schema",
                            "visibility",
                            "producer",
                        }
                    )
                ),
            )
            request = request.model_copy(update={"context_configuration_ref": raw_ref})
        else:
            changed = put(
                task.admission.data.store,
                {"changed_original": True},
                "model-binding/1" if fault == "route" else "model-parameters/1",
            )
            profiles = tuple(
                p.model_copy(
                    update={
                        (
                            "routing_ref" if fault == "route" else "configuration_ref"
                        ): changed
                    }
                )
                for p in config.profiles
            )
            config = ActorContextConfiguration.model_validate(
                config.model_copy(update={"profiles": profiles})
            )
            changes: dict[str, object] = {
                "context_configuration_ref": put(
                    task.admission.data.store, config, "actor-context-configuration/1"
                )
            }
            if fault == "parameters":
                changes["parameters_refs"] = (changed,) * len(request.parameters_refs)
            request = ActorRunRequest.model_validate(request.model_copy(update=changes))
    elif fault == "round":
        request = request.model_copy(update={"revision_round": 1})
    else:
        raw = request.model_dump()
        raw["schema_version"] = "actor-run-request/1"
        for name in ("candidate_id", "revision_round", "context_configuration_ref"):
            raw.pop(name)
        request = ActorRunRequest.model_validate(raw)
    task.phases.initialized = InitializedTask.model_validate(
        task.phases.initialized.model_copy(update={"actor": request})
    )
    before = len(c.native.channel.sent)
    with pytest.raises(TaskExecutionUnconfirmed) as caught:
        execute_task(task.plan, task.deps)
    assert caught.value.primary is not None
    assert (
        c.native.loader.session.calls == task.browser.calls == 0
        and len(c.native.channel.sent) == before
    )
    assert task.phases.calls[-3:] == ["close", "verify_closed", "restore"]
    assert "reset" in caught.value.known
    c.native.client.close(
        task.deps.controls.bind(
            command("close-admission-refused", attempt=request.scope.attempt_id)
        )
    )


@pytest.mark.parametrize("outcome", ["over_limit", "unknown_count"])
def test_current_task_budget_refusal_or_unknown_count_never_creates_generation_or_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    c = current_task_case(tmp_path / outcome, monkeypatch)
    if outcome == "over_limit":
        c.native.loader.session.tokens = tuple(range(28673))
    else:
        c.native.channel.broken_reply = b"unknown original count reply"
    task = c.task
    with pytest.raises(TaskExecutionUnconfirmed) as caught:
        execute_task(task.plan, task.deps)
    assert isinstance(caught.value.primary, ActorLoopFailure)
    assert (
        caught.value.evaluation is None
        and c.native.loader.session.calls == task.browser.calls == 0
    )
    operations = [decode_worker_command(raw).operation for raw in c.native.channel.sent]
    assert operations.count("measure") == 1 and "generate" not in operations
    snapshot = cast(TraceSnapshot, caught.value.trace)
    assert not any(isinstance(event, GenerationPlanned) for event in snapshot.events)
    sent = len(c.native.channel.sent)
    with pytest.raises(DispatchAlreadyCommitted):
        execute_task(task.plan, task.deps)
    assert len(c.native.channel.sent) == sent
    if outcome == "over_limit":
        c.native.client.close(
            task.deps.controls.bind(command("close-task-budget-refused"))
        )
    else:
        assert c.native.channel.aborts == 1


@pytest.mark.parametrize("bad", [None, True, "", [], {}, 7])
def test_invalid_task_actor_contracts_fail_before_dependencies(bad: object) -> None:
    with pytest.raises(ValidationError):
        ConstructionTaskActorAuthority(
            cast(TaskExecutionPlan, bad),
            cast(InitializedTask, object()),
            cast(PreparedActorInput, object()),
            cast(TaskActorAdmissionDeps, object()),
        )


def test_current_task_repeat_cannot_rebind_completed_or_unknown_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = current_task_case(tmp_path / "repeat", monkeypatch)
    result = execute_task(c.task.plan, c.task.deps)
    assert result.generations == 1
    before = len(c.native.channel.sent)
    with pytest.raises(DispatchAlreadyCommitted):
        execute_task(c.task.plan, c.task.deps)
    assert len(c.native.channel.sent) == before and c.native.loader.session.calls == 1
    c.native.client.close(c.task.deps.controls.bind(command("close-task-repeat")))


def test_verified_return_collection_repeats_exact_fact_and_refuses_changed_original_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = current_task_case(tmp_path / "returns", monkeypatch)
    execute_task(c.task.plan, c.task.deps)
    execution = c.completed[0]

    class UnitParentProof:
        def __init__(self) -> None:
            self.calls = 0

        def verify_return(self, value: LocalActorExecution, control: object) -> None:
            self.calls += 1

    parent = UnitParentProof()
    observed: list[LocalActorExecution] = []
    recorder = RetainedActorReturns(cast(TraceActorAuthority, parent), observed)
    control = c.task.deps.controls.bind(command("readonly-original-return"))
    recorder.verify_return(execution, control)
    recorder.verify_return(execution, control)
    assert observed == [execution] and parent.calls == 2
    changed = LocalActorExecution.model_validate(
        execution.model_copy(
            update={
                "output": execution.output.model_copy(
                    update={"text": "changed original output"}
                )
            }
        )
    )
    with pytest.raises(OwnershipConflict):
        recorder.verify_return(changed, control)
    assert observed == [execution] and parent.calls == 3
    assert c.native.loader.session.calls == 1
    c.native.client.close(c.task.deps.controls.bind(command("close-return-collection")))
