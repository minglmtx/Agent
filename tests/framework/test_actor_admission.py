"""Actual journals and evidence: prepare a view, never dispatch or change state."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError
from lab_generate_skill.application.admit_candidate import prepare_actor_input
from lab_generate_skill.domain.actor_admission import (
    ActorAdmissionRequest,
    CandidateFacts,
)
from lab_generate_skill.domain.actor_inputs import ActorInput
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    InvalidTransition,
    OperationStopped,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.execution import AttemptStage
from lab_generate_skill.domain.lifecycle import CancellationRef, OperationContext
from lab_generate_skill.domain.observation import ResolvedObservation
from lab_generate_skill.ports.observations import Observations
from lab_generate_skill.runtime.lifecycle import OperationGuards
from actor_admission_fixtures import fixture
from test_lifecycle import ManualClock
from test_run_journal import command


class FixedInputs:
    def __init__(self, facts: CandidateFacts) -> None:
        self.facts = facts

    def load(
        self, equivalence_ref: EvidenceRef, skill_ref: EvidenceRef, op: OperationContext
    ) -> CandidateFacts:
        return self.facts


def test_actual_graph_admits_only_public_input_and_repeat_has_no_effects(
    tmp_path: Path,
) -> None:
    data = fixture(tmp_path)
    run_before = data.harness.path.read_bytes()
    progress = data.deps.construction.read(data.request.read_operation)
    blobs = set((tmp_path / "evidence" / "blobs").iterdir())
    first = prepare_actor_input(data.request, data.deps)
    assert prepare_actor_input(data.request, data.deps) == first
    assert data.authority.calls == 2
    assert first.binding == data.request.intent.binding
    assert first.run_revision == data.snapshot.revision
    assert first.construction_revision == progress.revision
    assert first.actor_input.skill == progress.project().candidates[0].response.skill
    assert (
        first.actor_input.initial_observation.record
        == data.inputs.candidate_inputs.observation
    )
    assert (
        first.actor_input.source_context_id
        != first.actor_input.initial_observation.record.context_id
    )
    assert set(first.actor_input.model_dump()) == {
        "schema_version",
        "source_context_id",
        "task",
        "skill",
        "initial_observation",
    }
    assert (
        ActorInput.model_validate_json(first.actor_input.model_dump_json())
        == first.actor_input
    )
    assert data.harness.path.read_bytes() == run_before
    assert data.deps.construction.read(data.request.read_operation) == progress
    assert set((tmp_path / "evidence" / "blobs").iterdir()) == blobs


@pytest.mark.parametrize("status", ["fail", "unknown", "missing"])
def test_failed_or_incomplete_equivalence_cannot_admit(
    tmp_path: Path, status: str
) -> None:
    data = fixture(tmp_path, comparison_status=status)
    before = data.harness.path.read_bytes()
    with pytest.raises(InvalidTransition, match="Unknown/rejected"):
        prepare_actor_input(data.request, data.deps)
    assert data.authority.calls == 0
    assert data.harness.path.read_bytes() == before


@pytest.mark.parametrize("stage", ["preparing", "executing"])
def test_attempt_must_be_at_exact_initial_gate(tmp_path: Path, stage: str) -> None:
    data = fixture(tmp_path, stage=cast(AttemptStage, stage))
    with pytest.raises(InvalidTransition, match="baseline-verified"):
        prepare_actor_input(data.request, data.deps)
    assert data.authority.calls == 0


def test_exact_baseline_and_comparison_must_be_recorded(tmp_path: Path) -> None:
    data = fixture(tmp_path, record_facts=False)
    with pytest.raises(OwnershipConflict, match="persist these exact"):
        prepare_actor_input(data.request, data.deps)


def test_live_authority_rejection_preserves_journals(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    data.authority.denied = True
    before = data.harness.path.read_bytes()
    with pytest.raises(OwnershipConflict, match="permission denied"):
        prepare_actor_input(data.request, data.deps)
    assert data.authority.calls == 1
    assert data.harness.path.read_bytes() == before


def test_concurrent_run_transition_invalidates_prepared_view(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    entry = data.harness.attempt_entry(
        data.snapshot, data.request.intent.binding.attempt_id, "executing"
    )

    def advance() -> None:
        data.deps.runs.append(entry, data.snapshot.revision, entry.event.operation)

    data.authority.callback = advance
    with pytest.raises(RevisionConflict, match="changed during"):
        prepare_actor_input(data.request, data.deps)
    current = data.deps.runs.read(command())
    assert current.revision == data.snapshot.revision + 1
    assert current.project()[1][0].stage == "executing"


@pytest.mark.parametrize("fault", ["missing", "corrupt"])
@pytest.mark.parametrize("item", ["skill", "baseline", "comparison", "source_reset"])
def test_broken_actual_graph_stops_before_authority(
    tmp_path: Path, fault: str, item: str
) -> None:
    data = fixture(tmp_path)
    targets = {
        "skill": data.request.skill_ref,
        "baseline": data.inputs.candidate_ref,
        "comparison": data.inputs.checks_ref,
        "source_reset": data.inputs.source_inputs.reset_ref,
    }
    path = tmp_path / "evidence" / "blobs" / targets[item].sha256
    if fault == "missing":
        path.unlink()
    else:
        path.write_bytes(b"broken")
    before = data.harness.path.read_bytes()
    with pytest.raises(
        EvidenceNotFound if fault == "missing" else EvidenceIntegrityError
    ):
        prepare_actor_input(data.request, data.deps)
    assert data.authority.calls == 0
    assert data.harness.path.read_bytes() == before


def test_wrong_pending_attempt_and_reused_operation_rejected(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    wrong = data.request.intent.model_copy(update={"skill_digest": "0" * 64})
    with pytest.raises(OwnershipConflict, match="pending construction"):
        prepare_actor_input(
            data.request.model_copy(update={"intent": wrong}), data.deps
        )
    reused = data.request.operation.model_copy(
        update={"operation_id": data.inputs.candidate.operation.operation_id}
    )
    with pytest.raises(OwnershipConflict, match="reuse a recorded"):
        prepare_actor_input(
            data.request.model_copy(update={"operation": reused}), data.deps
        )


def test_replacement_input_port_cannot_mix_valid_facts(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    facts = data.reader.load(
        data.request.equivalence_ref, data.request.skill_ref, data.request.operation
    )
    variants: list[dict[str, object]] = [
        {
            "equivalence_ref": facts.equivalence_ref.model_copy(
                update={"producer": "other"}
            )
        },
        {
            "equivalence": facts.equivalence.model_copy(
                update={"source_context_receipt_ref": facts.equivalence_ref}
            )
        },
        {
            "task_binding": facts.task_binding.model_copy(
                update={"registration_id": "other"}
            )
        },
        {"skill": facts.skill.model_copy(update={"title": "Another valid skill"})},
        {
            "observation": facts.observation.model_copy(
                update={
                    "record": facts.observation.record.model_copy(
                        update={"context_id": "other"}
                    )
                }
            )
        },
    ]
    for change in variants:
        changed = facts.model_copy(update=change)
        with pytest.raises((OwnershipConflict, ValidationError)):
            prepare_actor_input(
                data.request, replace(data.deps, inputs=FixedInputs(changed))
            )
    assert data.authority.calls == 0


def test_observation_port_cannot_replace_actual_record(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    observed = data.inputs.candidate_inputs.observation
    changed = observed.model_copy(update={"text": "replaced public text"})

    class OtherObservation:
        def load(self, ref: EvidenceRef, op: OperationContext) -> ResolvedObservation:
            return ResolvedObservation(record=changed, text=changed.text)

    data.reader.observations = cast(Observations, OtherObservation())
    with pytest.raises(OwnershipConflict, match="different initial record"):
        prepare_actor_input(data.request, data.deps)
    assert data.authority.calls == 0


def test_expired_deadline_stops_before_authority(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    past = data.request.operation.model_copy(
        update={"deadline": datetime.now(timezone.utc) - timedelta(seconds=1)}
    )
    with pytest.raises(OperationStopped):
        prepare_actor_input(
            data.request.model_copy(update={"operation": past}), data.deps
        )
    assert data.authority.calls == 0


@pytest.mark.parametrize("stop", ["deadline", "cancel"])
def test_stop_during_authority_cannot_return_actor_input(
    tmp_path: Path, stop: str
) -> None:
    data = fixture(tmp_path)
    clock = ManualClock()
    clock.wall = datetime.now(timezone.utc)
    op = data.request.operation.model_copy(
        update={
            "cancellation_ref": CancellationRef(
                channel_id="stop", run_id="run", owner_id="owner"
            )
        }
    )
    request = data.request.model_copy(update={"operation": op})
    deps = replace(data.deps, controls=OperationGuards(clock, data.harness.cancel))
    before = data.harness.path.read_bytes()

    def stop_now() -> None:
        if stop == "deadline":
            clock.sleep(61)
        else:
            data.harness.cancel.cancelled = True

    data.authority.callback = stop_now
    with pytest.raises(OperationStopped):
        prepare_actor_input(request, deps)
    assert data.authority.calls == 1
    assert data.harness.path.read_bytes() == before


def test_strict_request_contract_rejects_illegal_commands_and_shapes(
    tmp_path: Path,
) -> None:
    data = fixture(tmp_path)
    original = data.request
    changes: list[dict[str, object]] = [
        {"operation": original.operation.model_copy(update={"attempt_id": "other"})},
        {
            "operation": command(
                "cleanup-admit",
                attempt=original.intent.binding.attempt_id,
                cleanup_parent="old",
            )
        },
        {"operation": original.operation.model_copy(update={"owner_id": "other"})},
        {"read_operation": original.operation},
        {
            "read_operation": original.read_operation.model_copy(
                update={"run_id": "other"}
            )
        },
        {"skill_ref": original.skill_ref.model_copy(update={"visibility": "private"})},
        {"intent": None},
        {"intent": []},
        {"intent": {}},
        {"schema_version": "actor-admission-request/0"},
    ]
    for change in changes:
        with pytest.raises((OwnershipConflict, ValidationError)):
            ActorAdmissionRequest.model_validate(original.model_copy(update=change))
    invalid_inputs: tuple[object, ...] = (None, [], "", 42)
    for invalid in invalid_inputs:
        with pytest.raises(ValidationError):
            ActorAdmissionRequest.model_validate(invalid)
    with pytest.raises(ValidationError):
        ActorAdmissionRequest.model_validate(
            {**original.model_dump(), "private_extra": "unexpected"}
        )


def test_public_contract_initial_boundaries_and_private_fields(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    actor = prepare_actor_input(data.request, data.deps).actor_input
    observed = actor.initial_observation.record
    for change in (
        {"sequence": 1},
        {"state": "loading"},
        {"last_action_error": "failed"},
        {"attempt_id": ""},
        {"sequence": True},
    ):
        changed = actor.initial_observation.model_copy(
            update={"record": observed.model_copy(update=change)}
        )
        with pytest.raises(ValidationError):
            ActorInput.model_validate(
                actor.model_copy(update={"initial_observation": changed})
            )
    empty = observed.model_copy(update={"text": "", "text_ref": None})
    accepted = ActorInput.model_validate(
        actor.model_copy(
            update={"initial_observation": ResolvedObservation(record=empty, text="")}
        )
    )
    assert accepted.initial_observation.text == ""
    with pytest.raises(ValidationError):
        ActorInput.model_validate(
            {**actor.model_dump(), "claim_ref": data.data.plan.claim_ref}
        )
