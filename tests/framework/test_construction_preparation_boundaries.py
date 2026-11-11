"""Preparation/store/read boundaries; no alternative dispatch or generator."""

from dataclasses import replace
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.application.construction_preparation import (
    prepare_generator_step,
    GenerationPreparationUnconfirmed,
    GenerationPreparationDeps,
)
from lab_generate_skill.domain.construction_preparation import GeneratorPreparation
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    RevisionConflict,
    InvalidTransition,
    OperationStopped,
    EvidenceIntegrityError,
)
from construction_preparation_fixtures import preparation_case, PreparationCase


@pytest.fixture(scope="module")
def ready(tmp_path_factory: pytest.TempPathFactory) -> Any:
    c = preparation_case(tmp_path_factory.mktemp("preparation") / "case")
    request = c.request()
    return c, request, prepare_generator_step(request, c.deps)


@pytest.mark.parametrize("bad", [None, {}, [], "", True, 0])
def test_empty_or_wrong_type_request_rejects_before_dependencies(
    ready: Any, bad: Any
) -> None:
    c, request, saved = ready
    with pytest.raises(ValidationError):
        prepare_generator_step(bad, c.deps)
    c.native.assert_no_inference()


@pytest.mark.parametrize(
    "fault",
    [
        "version",
        "run-owner",
        "attempt",
        "cleanup",
        "invoke-owner",
        "same-id",
        "completion-parent",
        "revision-bool",
        "revision-extreme",
    ],
)
def test_command_version_scope_ids_and_extremes_are_strict(
    ready: Any, fault: str
) -> None:
    c, request, saved = ready
    data = request.model_dump()
    if fault == "version":
        data["schema_version"] = "construction-generation-preparation/0"
    elif fault == "revision-bool":
        data["expected_revision"] = True
    elif fault == "revision-extreme":
        data["expected_revision"] = 256
    elif fault == "same-id":
        data["invoke_operation"] = request.operation
    else:
        field = (
            "completion_operation"
            if fault == "completion-parent"
            else "invoke_operation" if fault == "invoke-owner" else "operation"
        )
        change = {
            "run-owner": {"owner_id": "foreign"},
            "attempt": {"attempt_id": "foreign"},
            "cleanup": {"mode": "cleanup", "parent_operation_id": "foreign"},
            "invoke-owner": {"owner_id": "foreign"},
            "completion-parent": {"parent_operation_id": "foreign"},
        }[fault]
        data[field] = getattr(request, field).model_copy(update=change)
    with pytest.raises(ValidationError):
        GeneratorPreparation.model_validate(data)
    c.native.assert_no_inference()


@pytest.mark.parametrize("state", ["stale", "stop", "claim"])
def test_live_original_state_and_claim_remain_required_without_writes(
    tmp_path: Path, state: str
) -> None:
    c = preparation_case(tmp_path / "case")
    request = c.request()
    if state == "stale":
        request = request.model_copy(update={"expected_revision": 0})
    elif state == "stop":
        c.native.stop()
    else:
        c.native.data.claim_authority.denied = True
    with pytest.raises(GenerationPreparationUnconfirmed) as caught:
        prepare_generator_step(request, c.deps)
    assert caught.value.phase == "admission" and not caught.value.retained
    assert isinstance(
        caught.value.primary,
        {
            "stale": RevisionConflict,
            "stop": InvalidTransition,
            "claim": OwnershipConflict,
        }[state],
    )
    c.native.assert_no_inference()


@pytest.mark.parametrize("reason", ["CANCELLED", "DEADLINE_EXCEEDED"])
def test_cancel_timeout_preserve_original_cause_without_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    c = preparation_case(tmp_path / "case")
    request = c.request()
    control = c.control.controls.bind(request.operation)
    error = OperationStopped(reason, "original-preparation-stop")

    def stopped() -> float:
        raise error

    monkeypatch.setattr(control, "checkpoint", stopped)
    with pytest.raises(GenerationPreparationUnconfirmed) as caught:
        prepare_generator_step(request, c.deps)
    assert caught.value.primary is error and not caught.value.retained
    c.native.assert_no_inference()


@pytest.mark.parametrize("stage", [1, 2, 3])
def test_partial_metadata_publication_retains_known_refs_no_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: int
) -> None:
    c = preparation_case(tmp_path / "case")
    request = c.request()
    original = c.native.data.store.put
    writes = 0
    error = OSError("metadata committed, acknowledgement lost")

    def lost(
        raw: bytes,
        metadata: EvidenceMetadata,
        control: Any = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        nonlocal writes
        ref = original(raw, metadata, control, exchange_id=exchange_id)
        writes += 1
        if writes == stage:
            raise error
        return ref

    with monkeypatch.context() as patch:
        patch.setattr(c.native.data.store, "put", lost)
        with pytest.raises(GenerationPreparationUnconfirmed) as caught:
            prepare_generator_step(request, c.deps)
    assert caught.value.primary is error and len(caught.value.retained) == stage
    assert (
        caught.value.phase
        == ["publish_input", "publish_parameters", "publish_step"][stage - 1]
    )
    c.native.assert_no_inference()
    if stage == 3:
        ref = caught.value.retained[-1]
        read = c.records.load(
            ref,
            request.run,
            request.operation,
            control=c.control.controls.bind(request.operation),
        )
        assert read.reference == ref
        c.native.assert_no_inference()


@pytest.mark.parametrize("scope", ["owner", "parent"])
def test_saved_step_read_cannot_change_owner_or_parent(ready: Any, scope: str) -> None:
    c, request, saved = ready
    operation = request.operation.cleanup(
        "wrong-read-" + scope, now=datetime.now(timezone.utc), seconds=60
    )
    operation = operation.model_copy(
        update=(
            {"owner_id": "foreign"}
            if scope == "owner"
            else {"parent_operation_id": "foreign"}
        )
    )
    with pytest.raises(OwnershipConflict):
        c.records.load(
            saved.reference,
            request.run,
            operation,
            control=c.control.controls.bind(operation),
        )
    c.native.assert_no_inference()


@pytest.mark.parametrize("fault", ["visibility", "media", "zero", "huge"])
def test_saved_step_requires_complete_private_bounded_JSON(
    ready: Any, fault: str
) -> None:
    c, request, saved = ready
    changes = {
        "visibility": {"visibility": "public"},
        "media": {"media_type": "text/plain"},
        "zero": {"size_bytes": 0},
        "huge": {"size_bytes": 4 * 1024**2 + 1},
    }[fault]
    ref = saved.reference.model_copy(update=changes)
    op = request.operation.cleanup(
        "bad-ref-" + fault, now=datetime.now(timezone.utc), seconds=60
    )
    with pytest.raises(ValueError if fault == "visibility" else EvidenceIntegrityError):
        c.records.load(ref, request.run, op, control=c.control.controls.bind(op))
    c.native.assert_no_inference()


def test_history_race_during_public_input_read_rejects_before_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = preparation_case(tmp_path / "case")
    request = c.request()
    read = c.deps.inputs.prepare

    def raced(plan: Any, op: Any, control: Any) -> Any:
        value = read(plan, op, control)
        current = c.control.journal.read(op)
        event = c.native.event
        c.control.journal.append(event, current.revision, event.operation)
        return value

    monkeypatch.setattr(c.deps.inputs, "prepare", raced)
    with pytest.raises(GenerationPreparationUnconfirmed) as caught:
        prepare_generator_step(request, c.deps)
    assert (
        isinstance(caught.value.primary, RevisionConflict) and not caught.value.retained
    )
    c.native.assert_no_inference()
