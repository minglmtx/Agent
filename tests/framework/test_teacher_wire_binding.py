"""Teacher wire parameters must match the original seed and reserved output.

Synthetic full wire/token/source fixture; no actual model, route, API or fee.
"""

from pathlib import Path
import pytest
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from teacher_revision_fixtures import revision_case


@pytest.mark.parametrize("seed", [None, 43, 45])
def test_missing_or_changed_original_teacher_wire_seed_refused_before_reserve(
    tmp_path: Path, seed: int | None
) -> None:
    case = revision_case(tmp_path / "case", parameter_seed=seed)
    with pytest.raises((OwnershipConflict, EvidenceIntegrityError)):
        case.plans.load(
            case.plan.revision.request_id,
            case.plan.send.operation,
            control=case.controls.bind(case.plan.send.operation),
        )
    assert not case.transport.calls
    assert not list((tmp_path / "case" / "ledger").iterdir())


@pytest.mark.parametrize("maximum", [16, 18])
def test_actual_teacher_output_limit_must_match_reserved_profile_before_reserve(
    tmp_path: Path, maximum: int
) -> None:
    case = revision_case(tmp_path / "case", parameter_output_tokens=maximum)
    with pytest.raises((OwnershipConflict, EvidenceIntegrityError)):
        case.plans.load(
            case.plan.revision.request_id,
            case.plan.send.operation,
            control=case.controls.bind(case.plan.send.operation),
        )
    assert not case.transport.calls
    assert not list((tmp_path / "case" / "ledger").iterdir())
