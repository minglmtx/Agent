"""Existing native worker/complete-count consumer with independent body gates."""

from pathlib import Path
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_context_count import ActorTokenCount
from lab_generate_skill.domain.context_budget import TokenMeasurement
from lab_generate_skill.domain.errors import (
    ActorInputBudgetExceeded,
    EvidenceIntegrityError,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.adapters.models.actor_count_protocol import (
    decode_worker_command,
)
from lab_generate_skill.domain.actor_context_count import ActorCountExecution
from lab_generate_skill.domain.context_budget import CountedContextInput
from test_actor_count_evidence import reviewer
from actor_context_fixtures import counter_case
from actor_engine_fixtures import setup
from adaptive_observation_fixtures import ObservationSession, prompt


@pytest.mark.parametrize(
    "body_count,whole_count,allowed",
    [(8, 100, True), (9, 100, False), (8, 101, False), (9, 101, False), (0, 100, True)],
)
def test_native_local_and_complete_request_budgets_are_separate(
    tmp_path: Path, body_count: int, whole_count: int, allowed: bool
) -> None:
    engine, loader, _, params, control = setup(tmp_path)
    session = ObservationSession()
    session.tokens = (1,) * whole_count
    session.body_tokens = (2,) * body_count
    loader.session = session
    request = prompt()
    measured = engine.measure(request, params, control)
    measured.verify(request, params, engine.artifact, engine.config)
    assert measured.schema_version == "actor-token-count/2"
    assert (
        measured.input_tokens == whole_count
        and measured.observation_tokens == body_count
    )
    assert request.observation_view is not None
    assert measured.observation_body_sha256 == request.observation_view.body_sha256
    assert session.body_calls == [
        request.observation_view.body(request.messages[1].content)
    ]
    if allowed:
        engine.validate(request, params, control)
    else:
        with pytest.raises(ActorInputBudgetExceeded):
            engine.validate(request, params, control)
        # Capacity refusal is not a broken native session, inference or retry.
        assert session.closed == 0
    assert session.calls == 0 and loader.loads == 1
    engine.close(control)
    assert session.closed == 1


def test_compact_full_does_not_load_a_local_counter_or_change_legacy_wire(
    tmp_path: Path,
) -> None:
    engine, loader, old, params, control = setup(tmp_path)
    raw = old.model_dump_json()
    assert "observation_view" not in raw
    assert ActorPrompt.model_validate_json(raw).model_dump_json() == raw
    old_count = engine.measure(old, params, control)
    assert old_count.schema_version == "actor-token-count/1"
    assert "observation_tokens" not in old_count.model_dump_json()
    assert (
        engine.measure(prompt(local=False), params, control).schema_version
        == "actor-token-count/1"
    )
    assert loader.loads == 1 and loader.session.calls == 0
    with pytest.raises(ValidationError):
        ActorPrompt.model_validate({**old.model_dump(), "observation_view": None})
    with pytest.raises(ValidationError):
        ActorTokenCount.model_validate(
            {**old_count.model_dump(), "observation_tokens": None}
        )
    engine.close(control)


@pytest.mark.parametrize(
    "fault", ["unsupported", "wrong_tokens", "cancel", "failure", "cleanup"]
)
def test_local_native_failure_closes_original_once_and_never_reloads(
    tmp_path: Path, fault: str
) -> None:
    engine, loader, _, params, control = setup(tmp_path)
    if fault != "unsupported":
        session = ObservationSession()
        loader.session = session
        if fault == "wrong_tokens":
            session.body_tokens = cast(tuple[int, ...], (True,))
        else:
            session.body_failure = (
                OperationStopped("CANCELLED", "body-count")
                if fault == "cancel"
                else RuntimeError("body tokenizer failed")
            )
            if fault == "cleanup":
                session.cleanup_failure = OSError("native close failed")
    with pytest.raises(
        (EvidenceIntegrityError, OperationStopped, RuntimeError, BaseExceptionGroup)
    ) as caught:
        engine.measure(prompt(), params, control)
    if fault == "cleanup":
        assert isinstance(caught.value, BaseExceptionGroup)
        assert caught.value.exceptions == (
            session.body_failure,
            session.cleanup_failure,
        )
    assert loader.session.calls == 0 and loader.session.closed == 1
    with pytest.raises(OwnershipConflict):
        engine.measure(prompt(), params, control)
    assert loader.loads == 1


def test_existing_count_publication_saves_native_body_and_whole_request_facts(
    tmp_path: Path,
) -> None:
    case = counter_case(tmp_path)
    session = ObservationSession()
    case.loader.session = session
    request = prompt()
    input_ref = case.put(request.model_dump_json().encode(), "actor-model-input/1")
    counted = case.counter.measure(
        input_ref, case.profile, case.policy, control=case.control
    )
    assert counted.measurement.schema_version == "context-token-measurement/2"
    assert (
        counted.measurement.input_tokens == 3
        and counted.measurement.observation_tokens == 2
    )
    assert request.observation_view is not None
    assert (
        counted.measurement.observation_body_sha256
        == request.observation_view.body_sha256
    )
    assert (
        TokenMeasurement.model_validate_json(counted.measurement.model_dump_json())
        == counted.measurement
    )
    assert case.loader.loads == 1 and session.calls == 0
    commands = [decode_worker_command(raw) for raw in case.channel.sent]
    assert [c.operation for c in commands] == ["configure", "measure"]
    case.client.close(case.control)


@pytest.mark.parametrize(
    "tamper", [None, "observation_tokens", "observation_body_sha256"]
)
def test_closed_native_body_review_uses_original_frames_without_live_recount(
    tmp_path: Path, tamper: str | None
) -> None:
    case = counter_case(tmp_path)
    session = ObservationSession()
    case.loader.session = session
    reference = case.put(prompt().model_dump_json().encode(), "actor-model-input/1")
    counted = case.counter.measure(
        reference, case.profile, case.policy, control=case.control
    )
    closed_review = reviewer(case)
    case.client.close(case.control)
    sent = len(case.channel.sent)
    if tamper is not None:
        execution = ActorCountExecution.model_validate_json(
            case.evidence.read(counted.evidence_ref, case.control)
        )
        changed = counted.measurement.model_copy(
            update={tamper: 3 if tamper == "observation_tokens" else "0" * 64}
        )
        forged = execution.model_copy(update={"measurement": changed})
        counted = CountedContextInput(
            measurement=changed,
            evidence_ref=case.put(
                forged.model_dump_json().encode(), forged.schema_version
            ),
        )
        with pytest.raises(EvidenceIntegrityError):
            closed_review.verify(
                counted, case.profile, case.policy, control=case.control
            )
    else:
        assert (
            closed_review.verify(
                counted, case.profile, case.policy, control=case.control
            )
            == counted.measurement
        )
    assert len(case.channel.sent) == sent and session.calls == 0 and session.closed == 1


def test_read_count_probe_can_be_measured_but_never_inferred(tmp_path: Path) -> None:
    engine, loader, _, params, control = setup(tmp_path)
    session = ObservationSession()
    loader.session = session
    probe = prompt().model_copy(
        update={"prompt_version": "browsergym-adaptive-count-probe-v1"}
    )
    assert engine.measure(probe, params, control).observation_tokens == 2
    before = len(session.body_calls)
    for method in (engine.validate, engine.generate, engine.generate_prepared):
        with pytest.raises(OwnershipConflict):
            method(probe, params, control)
    assert (
        len(session.body_calls) == before and session.calls == 0 and loader.loads == 1
    )
    engine.close(control)


@pytest.mark.parametrize("field", ["observation_tokens", "observation_body_sha256"])
def test_legacy_and_teacher_counts_cannot_carry_adaptive_fields(
    tmp_path: Path, field: str
) -> None:
    case = counter_case(tmp_path)
    counted = case.counter.measure(
        case.input_ref, case.profile, case.policy, control=case.control
    )
    with pytest.raises(ValidationError):
        TokenMeasurement.model_validate(
            {**counted.measurement.model_dump(), field: None}
        )
    data = counted.measurement.model_dump() | dict(
        schema_version="context-token-measurement/2",
        role="teacher",
        observation_tokens=2,
        observation_body_sha256="a" * 64,
    )
    with pytest.raises(ValidationError):
        TokenMeasurement.model_validate(data)
    case.client.close(case.control)
