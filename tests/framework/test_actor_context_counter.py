"""Complete private bytes/profile binding, role isolation and bounded failures."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.models.context_tokens import ActorContextTokenCounter
from lab_generate_skill.domain.context_budget import ContextBudgetProfile
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.evidence import EvidenceRef
from actor_context_fixtures import counter_case
from context_budget_fixtures import selection


def test_complete_input_measurement_binds_policy_profile_bytes_and_reuses_worker(
    tmp_path: Path,
) -> None:
    case = counter_case(tmp_path)
    first_counted = case.counter.measure(
        case.input_ref, case.profile, case.policy, control=case.control
    )
    second_counted = case.counter.measure(
        case.input_ref, case.profile, case.policy, control=case.control
    )
    first, second = first_counted.measurement, second_counted.measurement
    assert (
        first.input_ref == case.input_ref
        and first.input_tokens == first.upper_bound_tokens == 3
    )
    assert (
        first.profile_sha256 == case.profile.digest
        and first.policy_sha256 == case.policy.digest
    )
    assert (
        first.complete_request
        and first.precision == "exact"
        and first.elapsed_seconds >= 0
    )
    assert first.model_dump(exclude={"elapsed_seconds"}) == second.model_dump(
        exclude={"elapsed_seconds"}
    )
    assert case.loader.loads == 1 and case.loader.session.calls == 0
    case.client.close(case.control)
    assert case.channel.finishes == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("model", "other-model"),
        ("provider", "other-provider"),
        ("tokenizer_sha256", "0" * 64),
        ("template_sha256", "0" * 64),
        ("counting_method", "teacher-estimate"),
        ("context_window", 201),
        ("output_reserve", 99),
        ("input_limit", 99),
        ("provider_input_limit", 99),
        ("uncounted_overhead", 1),
        ("soft_target", 79),
    ],
)
def test_frozen_profile_change_rejected_before_read_or_count(
    tmp_path: Path, field: str, value: object
) -> None:
    case = counter_case(tmp_path)
    foreign = ContextBudgetProfile.model_validate(
        {**case.profile.model_dump(), field: value}
    )
    sent = len(case.channel.sent)
    with pytest.raises(OwnershipConflict):
        case.counter.measure(case.input_ref, foreign, case.policy, control=case.control)
    assert len(case.channel.sent) == sent and case.loader.loads == 0
    case.client.close(case.control)


@pytest.mark.parametrize("fault", ["teacher-policy", "unacquired", "foreign-session"])
def test_role_and_original_acquired_route_are_required(
    tmp_path: Path, fault: str
) -> None:
    case = counter_case(tmp_path, configure=fault != "unacquired")
    sent = len(case.channel.sent)
    with pytest.raises(OwnershipConflict):
        if fault == "foreign-session":
            ActorContextTokenCounter(
                case.client,
                case.evidence,
                case.profile,
                case.binding,
                case.parameters,
                session_id="other",
            )
        else:
            case.counter.measure(
                case.input_ref,
                case.profile,
                (
                    selection(role="teacher").policy
                    if fault == "teacher-policy"
                    else case.policy
                ),
                control=case.control,
            )
    assert len(case.channel.sent) == sent and case.loader.loads == 0
    case.client.close(case.control)


@pytest.mark.parametrize(
    "change",
    [
        {"visibility": "teacher"},
        {"content_schema": "teacher-model-input/1"},
        {"media_type": "text/plain"},
        {"size_bytes": 0},
        {"size_bytes": 8 * 1024**2 + 1},
    ],
)
def test_invalid_input_metadata_has_no_worker_effect(
    tmp_path: Path, change: dict[str, object]
) -> None:
    case = counter_case(tmp_path)
    wrong = EvidenceRef.model_validate({**case.input_ref.model_dump(), **change})
    sent = len(case.channel.sent)
    with pytest.raises((ValueError, EvidenceIntegrityError)):
        case.counter.measure(wrong, case.profile, case.policy, control=case.control)
    assert len(case.channel.sent) == sent and case.loader.loads == 0
    case.client.close(case.control)


@pytest.mark.parametrize(
    "raw", [b"{}", b"[]", b"null", b"\xff", b'{"x":1,"x":2}', b'{"x":NaN}']
)
def test_malformed_or_wrong_schema_input_is_not_counted(
    tmp_path: Path, raw: bytes
) -> None:
    case = counter_case(tmp_path)
    reference = case.put(raw, "actor-model-input/1")
    sent = len(case.channel.sent)
    with pytest.raises((ValueError, UnicodeError)):
        case.counter.measure(reference, case.profile, case.policy, control=case.control)
    assert len(case.channel.sent) == sent and case.loader.loads == 0
    case.client.close(case.control)


def test_noncanonical_complete_input_is_not_silently_normalized(tmp_path: Path) -> None:
    case = counter_case(tmp_path)
    raw = b" " + case.evidence.read(case.input_ref, case.control)
    reference = case.put(raw, "actor-model-input/1")
    with pytest.raises(EvidenceIntegrityError):
        case.counter.measure(reference, case.profile, case.policy, control=case.control)
    assert case.loader.loads == 0
    case.client.close(case.control)


@pytest.mark.parametrize("fault", ["corrupt", "cancel", "timeout", "wrong-type"])
def test_evidence_read_failure_has_no_count_or_inference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    case = counter_case(tmp_path)

    def fail(reference: EvidenceRef, control: OperationControl) -> bytes:
        if fault in ("cancel", "timeout"):
            raise OperationStopped(
                "CANCELLED" if fault == "cancel" else "DEADLINE_EXCEEDED",
                "counter-read",
            )
        if fault == "wrong-type":
            return "wrong"  # type: ignore[return-value]
        return b"{}"

    monkeypatch.setattr(case.evidence, "read", fail)
    with pytest.raises((OperationStopped, EvidenceIntegrityError)):
        case.counter.measure(
            case.input_ref, case.profile, case.policy, control=case.control
        )
    assert len(case.channel.sent) == 1 and case.loader.loads == 0
    case.client.close(case.control)
