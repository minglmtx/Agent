"""Original Actor preparation input/identity/race/stop/uncertain publication gates."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.application.construction_task_preparation import (
    prepare_actor_step,
    ActorPreparationUnconfirmed,
)
from lab_generate_skill.domain.construction_task_preparation import ActorPreparation
from lab_generate_skill.domain.construction_control import ExecuteConstructionWork
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    RevisionConflict,
    OperationStopped,
)
from lab_generate_skill.policies.construction_attempt import original_attempt_intent
from construction_task_preparation_fixtures import task_preparation_case
from construction_storage_fixtures import put
from test_run_journal import command


@pytest.fixture(scope="module")
def ready(tmp_path_factory: pytest.TempPathFactory) -> Any:
    with pytest.MonkeyPatch.context() as patch:
        c = task_preparation_case(tmp_path_factory.mktemp("actor-work") / "case", patch)
    return c, c.request()


@pytest.mark.parametrize("bad", [None, {}, [], "", True, 0])
def test_empty_wrong_type_commands_reject_before_dependency_access(
    ready: Any, bad: Any
) -> None:
    c, _ = ready
    with pytest.raises(ValidationError):
        prepare_actor_step(bad, c.deps)
    assert (
        not c.current.task.phases.calls and c.current.native.loader.session.calls == 0
    )


@pytest.mark.parametrize(
    "fault",
    [
        "version",
        "owner",
        "attempt",
        "cleanup",
        "same-id",
        "completion-parent",
        "revision-bool",
        "revision-large",
        "task-run",
    ],
)
def test_original_command_schema_scope_and_operation_ids(
    ready: Any, fault: str
) -> None:
    c, request = ready
    data = request.model_dump()
    if fault == "version":
        data["schema_version"] = "construction-task-preparation/0"
    elif fault.startswith("revision"):
        data["expected_revision"] = True if fault == "revision-bool" else 256
    elif fault == "task-run":
        data["run"] = request.run.model_copy(update={"submission_key": "foreign"})
    elif fault == "same-id":
        data["completion_operation"] = request.operation
    elif fault == "completion-parent":
        data["completion_operation"] = request.completion_operation.model_copy(
            update={"parent_operation_id": "foreign"}
        )
    else:
        change = {
            "owner": {"owner_id": "foreign"},
            "attempt": {"attempt_id": "foreign"},
            "cleanup": {"mode": "cleanup", "parent_operation_id": "foreign"},
        }[fault]
        data["operation"] = request.operation.model_copy(update=change)
    with pytest.raises(ValidationError):
        ActorPreparation.model_validate(data)
    assert not c.current.task.phases.calls


@pytest.mark.parametrize("bad", ["", None, True, 0, "has space", "x" * 257])
def test_pure_intent_rejects_invalid_external_attempt_identity(
    ready: Any, bad: Any
) -> None:
    c, request = ready
    progress = c.control.journal.read(command())
    with pytest.raises(ValidationError):
        original_attempt_intent(progress, bad)


@pytest.mark.parametrize(
    "fault",
    [
        "claim",
        "context",
        "digest",
        "slot",
        "skill",
        "public-task",
        "skill-media",
        "stale",
        "claim-denied",
        "writer-denied",
    ],
)
def test_candidate_source_and_live_admission_mismatches_never_publish_or_execute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    c = task_preparation_case(tmp_path / "case", monkeypatch)
    request = c.request()
    intent = request.task.intent
    data = c.current.task.admission.data
    if fault in ("claim", "context"):
        ref = (
            intent.binding.claim_ref if fault == "claim" else intent.public_context_ref
        ).model_copy(update={"sha256": "0" * 64})
        intent = (
            intent.model_copy(
                update={"binding": intent.binding.model_copy(update={"claim_ref": ref})}
            )
            if fault == "claim"
            else intent.model_copy(update={"public_context_ref": ref})
        )
    elif fault in ("digest", "slot"):
        intent = intent.model_copy(
            update=(
                {"skill_digest": "0" * 64}
                if fault == "digest"
                else {"candidate_slot": 1}
            )
        )
    elif fault == "skill":
        skill = (
            c.control.journal.read(request.operation)
            .project()
            .candidates[1]
            .response.skill
        )
        request = request.model_copy(
            update={
                "task": request.task.model_copy(
                    update={
                        "skill_ref": put(data.store, skill, "compact-skill/1", "public")
                    }
                )
            }
        )
    elif fault == "public-task":
        ref = request.task.evaluation.public_task_ref.model_copy(
            update={"sha256": "0" * 64}
        )
        request = request.model_copy(
            update={
                "task": request.task.model_copy(
                    update={
                        "evaluation": request.task.evaluation.model_copy(
                            update={"public_task_ref": ref}
                        )
                    }
                )
            }
        )
    elif fault == "skill-media":
        ref = request.task.skill_ref.model_copy(update={"media_type": "text/plain"})
        request = request.model_copy(
            update={"task": request.task.model_copy(update={"skill_ref": ref})}
        )
    elif fault == "stale":
        request = request.model_copy(update={"expected_revision": 0})
    elif fault == "claim-denied":
        data.claim_authority.denied = True
    else:
        data.authority.denied = True
    request = request.model_copy(
        update={"task": request.task.model_copy(update={"intent": intent})}
    )
    with pytest.raises(ActorPreparationUnconfirmed) as caught:
        prepare_actor_step(request, c.deps)
    assert isinstance(
        caught.value.primary,
        RevisionConflict if fault == "stale" else OwnershipConflict,
    )
    assert not caught.value.retained
    assert (
        not c.current.task.phases.calls and c.current.native.loader.session.calls == 0
    )


@pytest.mark.parametrize("target", ["prepare", "invoke", "complete"])
@pytest.mark.parametrize("reason", ["CANCELLED", "DEADLINE_EXCEEDED"])
def test_original_operation_cancel_or_expiry_prevents_preparation_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str, reason: str
) -> None:
    c = task_preparation_case(tmp_path / "case", monkeypatch)
    request = c.request()
    op = {
        "prepare": request.operation,
        "invoke": request.task.operation,
        "complete": request.completion_operation,
    }[target]
    control = c.control.controls.bind(op)
    error = OperationStopped(reason, "original-task-preparation-stop")

    def stopped() -> float:
        raise error

    monkeypatch.setattr(control, "checkpoint", stopped)
    with pytest.raises(ActorPreparationUnconfirmed) as caught:
        prepare_actor_step(request, c.deps)
    assert caught.value.primary is error and not caught.value.retained
    assert not c.current.task.phases.calls


def test_lost_publication_ack_retains_original_step_for_readonly_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = task_preparation_case(tmp_path / "case", monkeypatch)
    request = c.request()
    store = c.current.task.admission.data.store
    original = store.put
    error = OSError("original task command committed, acknowledgement lost")

    def lost(
        raw: bytes,
        metadata: EvidenceMetadata,
        control: Any = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        original(raw, metadata, control, exchange_id=exchange_id)
        raise error

    with monkeypatch.context() as patch:
        patch.setattr(store, "put", lost)
        with pytest.raises(ActorPreparationUnconfirmed) as caught:
            prepare_actor_step(request, c.deps)
    assert caught.value.primary is error and caught.value.phase == "publish_step"
    assert len(caught.value.retained) == 1 and not c.current.task.phases.calls
    cleanup = request.operation.cleanup(
        "resolve-task-command-only", now=datetime.now(timezone.utc), seconds=60
    )
    saved = c.records.load(
        caught.value.retained[0],
        request.run,
        cleanup,
        control=c.control.controls.bind(cleanup),
    )
    assert saved.step == request.step() and c.current.native.loader.session.calls == 0


def test_journal_race_during_public_skill_read_fails_before_new_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = task_preparation_case(tmp_path / "case", monkeypatch)
    request = c.request()
    store = c.current.task.admission.data.store
    original = store.read
    raced = False

    def read(reference: EvidenceRef, control: Any = None) -> bytes:
        nonlocal raced
        raw = original(reference, control)
        if reference == request.task.skill_ref and not raced:
            raced = True
            work = request.step().work
            assert isinstance(work, ExecuteConstructionWork)
            c.control.journal.append(
                work.planned, request.expected_revision, request.operation
            )
        return raw

    with monkeypatch.context() as patch:
        patch.setattr(store, "read", read)
        with pytest.raises(ActorPreparationUnconfirmed) as caught:
            prepare_actor_step(request, c.deps)
    assert (
        isinstance(caught.value.primary, RevisionConflict) and not caught.value.retained
    )
    assert (
        not c.current.task.phases.calls and c.current.native.loader.session.calls == 0
    )
