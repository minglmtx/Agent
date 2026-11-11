"""Persist original count frames once, then independently read after closure."""

from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.models.context_count_review import (
    ActorContextCountReviewer,
)
from lab_generate_skill.adapters.models.context_tokens import (
    CountPersistenceUnconfirmed,
)
from lab_generate_skill.adapters.models.actor_count_protocol import (
    ActorCountReply,
    decode_worker_command,
)
from lab_generate_skill.domain.actor_context_count import ActorCountExecution
from lab_generate_skill.domain.context_budget import CountedContextInput
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.context_projection import ContextTokenCounter
from actor_context_fixtures import counter_case, CounterCase


def reviewer(case: CounterCase) -> ActorContextCountReviewer:
    guard, sources = case.client.owner_guard, case.client.installed_sources
    assert guard is not None and sources is not None
    return ActorContextCountReviewer(
        case.evidence,
        case.profile,
        case.binding,
        case.parameters,
        case.client.artifact,
        case.client.config,
        session_id="session",
        guard=guard,
        installed_sources=sources,
    )


def test_original_frames_review_after_close_needs_no_live_worker(
    tmp_path: Path,
) -> None:
    case = counter_case(tmp_path)
    counter: ContextTokenCounter = case.counter
    counted = counter.measure(
        case.input_ref, case.profile, case.policy, control=case.control
    )
    execution = ActorCountExecution.model_validate_json(
        case.evidence.read(counted.evidence_ref, case.control)
    )
    assert (
        case.evidence.read(execution.command_ref, case.control) == case.channel.sent[-1]
    )
    read_only = reviewer(case)
    case.client.close(case.control)
    sent = len(case.channel.sent)
    actual = read_only.verify(counted, case.profile, case.policy, control=case.control)
    assert actual.input_tokens == counted.measurement.input_tokens == 3
    assert case.loader.session.closed == 1 and case.loader.session.calls == 0
    assert len(case.channel.sent) == sent


@pytest.mark.parametrize("stage", [1, 2, 3])
@pytest.mark.parametrize("fault", ["lost-ack", "cancel", "foreign"])
def test_partial_publication_retains_original_exchange_and_candidate_refs_without_recount(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: int, fault: str
) -> None:
    case = counter_case(tmp_path)
    original = case.evidence.put
    writes = 0

    def put(
        data: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        nonlocal writes
        writes += 1
        actual = original(data, metadata, control, exchange_id=exchange_id)
        if writes == stage:
            if fault == "lost-ack":
                raise OSError("original count publication acknowledgement lost")
            if fault == "cancel":
                raise OperationStopped("CANCELLED", "count-publication")
            return actual.model_copy(update={"sha256": "0" * 64})
        return actual

    monkeypatch.setattr(case.evidence, "put", put)
    with pytest.raises(CountPersistenceUnconfirmed) as caught:
        case.counter.measure(
            case.input_ref, case.profile, case.policy, control=case.control
        )
    error = caught.value
    assert error.phase == ("save_command", "save_reply", "save_execution")[stage - 1]
    assert error.exchange.command == case.channel.sent[-1]
    assert (
        error.measurement.input_ref == case.input_ref
        and error.measurement.input_tokens == 3
    )
    assert len(error.retained) >= stage and writes == stage
    assert (
        sum(
            decode_worker_command(raw).operation == "measure"
            for raw in case.channel.sent
        )
        == 1
    )
    assert case.loader.session.calls == 0
    if stage == 3 and fault == "lost-ack":
        # Reconcile the exact already-written object read-only, never recount.
        original_fact = CountedContextInput(
            measurement=error.measurement, evidence_ref=error.retained[-1]
        )
        assert (
            reviewer(case)
            .verify(original_fact, case.profile, case.policy, control=case.control)
            .input_tokens
            == 3
        )
    case.client.close(case.control)


@pytest.mark.parametrize(
    "change",
    [
        {"visibility": "public"},
        {"content_schema": "teacher-context-count-execution/1"},
        {"media_type": "text/plain"},
        {"size_bytes": 0},
        {"size_bytes": 256 * 1024 + 1},
    ],
)
def test_counted_wrapper_requires_original_role_evidence(
    tmp_path: Path, change: dict[str, Any]
) -> None:
    case = counter_case(tmp_path)
    counted = case.counter.measure(
        case.input_ref, case.profile, case.policy, control=case.control
    )
    data = counted.model_dump()
    data["evidence_ref"] = {**counted.evidence_ref.model_dump(), **change}
    with pytest.raises(ValidationError):
        CountedContextInput.model_validate(data)
    case.client.close(case.control)


@pytest.mark.parametrize(
    "fault",
    [
        "measurement",
        "guard",
        "installation",
        "reply-count",
        "reply-identity",
        "command-tag",
    ],
)
def test_closed_reviewer_rejects_forged_or_foreign_count_lineage(
    tmp_path: Path, fault: str
) -> None:
    case = counter_case(tmp_path)
    counted = case.counter.measure(
        case.input_ref, case.profile, case.policy, control=case.control
    )
    read_only = reviewer(case)
    execution = ActorCountExecution.model_validate_json(
        case.evidence.read(counted.evidence_ref, case.control)
    )
    if fault == "measurement":
        wrong_measurement = counted.measurement.model_copy(
            update={"input_tokens": 4, "upper_bound_tokens": 4}
        )
        counted = CountedContextInput(
            measurement=wrong_measurement, evidence_ref=counted.evidence_ref
        )
    else:
        data = execution.model_dump()
        if fault == "guard":
            data["guard"] = execution.guard.model_copy(
                update={
                    "worker": execution.guard.worker.model_copy(
                        update={"process_id": execution.guard.worker.process_id + 1}
                    )
                }
            )
        elif fault == "installation":
            data["installed_sources"] = execution.installed_sources.model_copy(
                update={"release_id": "foreign"}
            )
        elif fault == "command-tag":
            data["command_ref"] = case.put(b"{}", "actor-context-count-command/1")
        else:
            reply = ActorCountReply.model_validate_json(
                case.evidence.read(execution.reply_ref, case.control)
            )
            reply_data = reply.model_dump()
            if fault == "reply-count":
                assert reply.measurement is not None
                reply_data["measurement"] = reply.measurement.model_copy(
                    update={"input_tokens": 4}
                )
            else:
                reply_data["command_sha256"] = "0" * 64
            wrong_reply = ActorCountReply.model_validate(reply_data)
            data["reply_ref"] = case.put(
                wrong_reply.model_dump_json().encode(), "actor-context-count-reply/1"
            )
        wrong_execution = ActorCountExecution.model_validate(data)
        counted = CountedContextInput(
            measurement=counted.measurement,
            evidence_ref=case.put(
                wrong_execution.model_dump_json().encode(),
                "actor-context-count-execution/1",
            ),
        )
    case.client.close(case.control)
    sent = len(case.channel.sent)
    with pytest.raises((ValueError, EvidenceIntegrityError, OwnershipConflict)):
        read_only.verify(counted, case.profile, case.policy, control=case.control)
    assert len(case.channel.sent) == sent


@pytest.mark.parametrize("fault", ["corrupt", "timeout", "cancel", "wrong-type"])
def test_closed_review_read_failure_never_opens_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    case = counter_case(tmp_path)
    counted = case.counter.measure(
        case.input_ref, case.profile, case.policy, control=case.control
    )
    read_only = reviewer(case)
    case.client.close(case.control)
    sent = len(case.channel.sent)

    def read(reference: EvidenceRef, control: OperationControl) -> bytes:
        if fault in ("timeout", "cancel"):
            raise OperationStopped(fault.upper(), "count-read-only")
        if fault == "wrong-type":
            return None  # type: ignore[return-value]
        return b"{}"

    monkeypatch.setattr(case.evidence, "read", read)
    with pytest.raises((EvidenceIntegrityError, OperationStopped)):
        read_only.verify(counted, case.profile, case.policy, control=case.control)
    assert len(case.channel.sent) == sent
