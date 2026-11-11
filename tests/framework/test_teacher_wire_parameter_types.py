"""Pure Teacher parameter binding: strict values, complete bytes, no I/O effects."""

import json
from pathlib import Path
from typing import cast
import pytest
from lab_generate_skill.adapters.models.teacher_request_binding import (
    verify_teacher_wire_parameters,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from teacher_revision_fixtures import revision_case


def test_exact_original_parameters_repeat_readonly_and_do_not_reserve(
    tmp_path: Path,
) -> None:
    case = revision_case(tmp_path / "case")
    raw = case.store.read(case.plan.send.parameters_ref)
    verify_teacher_wire_parameters(raw, case.plan)
    verify_teacher_wire_parameters(raw, case.plan)
    bound = case.plans.load(
        case.plan.revision.request_id,
        case.plan.send.operation,
        control=case.controls.bind(case.plan.send.operation),
    )
    assert bound.plan == case.plan
    assert case.counts.calls == 2 and not case.transport.calls
    assert not list((tmp_path / "case/ledger").iterdir())


@pytest.mark.parametrize(
    "field,value",
    [
        ("seed", True),
        ("seed", 44.0),
        ("seed", "44"),
        ("seed", None),
        ("max_tokens", True),
        ("max_tokens", 17.0),
        ("max_tokens", "17"),
        ("max_tokens", None),
        ("max_tokens", 0),
        ("max_tokens", 2147483647),
    ],
)
def test_wrong_numeric_type_empty_and_extreme_values_refused(
    tmp_path: Path, field: str, value: object
) -> None:
    case = revision_case(tmp_path / "case")
    parameters = {"seed": 44, "max_tokens": 17}
    raw = json.dumps({**parameters, field: value}).encode()
    with pytest.raises((OwnershipConflict, EvidenceIntegrityError)):
        verify_teacher_wire_parameters(raw, case.plan)
    assert not case.transport.calls
    assert not list((tmp_path / "case/ledger").iterdir())


@pytest.mark.parametrize(
    "raw",
    [
        None,
        False,
        17,
        "parameters",
        [],
        b"",
        b"null",
        b"[]",
        b"\xff",
        b'{"seed":44,"seed":44,"max_tokens":17}',
        b'{"seed":44,"max_tokens":NaN}',
        b" " * (1024**2 + 1),
    ],
    ids=[
        "none",
        "bool",
        "integer",
        "text",
        "list",
        "empty",
        "null",
        "array",
        "non_utf8",
        "duplicate",
        "nonfinite",
        "oversized",
    ],
)
def test_empty_wrong_type_duplicate_nonfinite_and_oversized_parameter_bytes_refused(
    tmp_path: Path, raw: object
) -> None:
    case = revision_case(tmp_path / "case")
    with pytest.raises((ValueError, TypeError, UnicodeError)):
        verify_teacher_wire_parameters(cast(bytes, raw), case.plan)
    assert not case.transport.calls
    assert not list((tmp_path / "case/ledger").iterdir())
