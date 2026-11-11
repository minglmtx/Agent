"""Declared coverage, missing/unknown semantics and strict fact boundaries."""

import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.evaluation import CheckResult
from lab_generate_skill.domain.state_checks import StateChecks, InitialStateSpec
from retrieval_fixtures import reference
from state_contract_fixtures import checks, specification


def test_complete_missing_failed_unknown_are_distinct() -> None:
    original = checks(("database", "mail"))
    assert original.status == "pass" and original.missing == ()
    missing = StateChecks(required=original.required, checks=original.checks[:1])
    assert missing.status == "unknown" and missing.missing == ("mail",)
    failed = original.checks[0].model_copy(update={"status": "fail"})
    assert (
        StateChecks(
            required=original.required, checks=(failed, original.checks[1])
        ).status
        == "fail"
    )
    assert StateChecks(required=original.required, checks=(failed,)).status == "unknown"
    unknown = CheckResult(name="database", status="unknown", reason_code="MISSING")
    assert (
        StateChecks(
            required=original.required, checks=(unknown, original.checks[1])
        ).status
        == "unknown"
    )
    assert StateChecks.model_validate_json(original.model_dump_json()) == original


@pytest.mark.parametrize(
    "fault",
    [
        "empty",
        "duplicate_required",
        "duplicate_results",
        "extra",
        "order",
        "no_evidence",
        "public",
        "teacher",
        "wrong_type",
        "bad_status",
    ],
)
def test_invalid_state_checks_rejected(fault: str) -> None:
    original = checks(("database", "mail"))
    values = original.model_dump()
    if fault == "empty":
        values["required"] = ()
    elif fault == "duplicate_required":
        values["required"] = ("database", "database")
    elif fault == "duplicate_results":
        values["checks"] = (original.checks[0],) * 2
    elif fault == "extra":
        values["checks"] = (original.checks[0].model_copy(update={"name": "other"}),)
    elif fault == "order":
        values["checks"] = tuple(reversed(original.checks))
    elif fault == "no_evidence":
        values["checks"] = (original.checks[0].model_copy(update={"evidence": ()}),)
    elif fault in ("public", "teacher"):
        values["checks"] = (
            original.checks[0].model_copy(
                update={"evidence": (reference({}, visibility=fault),)}
            ),
        )
    elif fault == "wrong_type":
        values["required"] = ["database", "mail"]
    else:
        values["checks"] = (original.checks[0].model_copy(update={"status": True}),)
    with pytest.raises(ValidationError):
        StateChecks.model_validate(values)


@pytest.mark.parametrize(
    "field",
    [
        "environment_checks",
        "preparation_checks",
        "initial_checks",
        "equivalence_checks",
        "task_reset_checks",
        "environment_reset_checks",
        "health_checks",
    ],
)
@pytest.mark.parametrize("value", [(), ("same", "same"), (None,), (True,)])
def test_every_spec_phase_has_explicit_valid_coverage(
    field: str, value: object
) -> None:
    with pytest.raises(ValidationError):
        InitialStateSpec.model_validate(
            specification().model_copy(update={field: value})
        )


def test_many_checks_do_not_silently_truncate_coverage() -> None:
    declared = tuple("check-" + str(i) for i in range(1024))
    actual = checks(declared)
    assert actual.status == "pass" and len(actual.checks) == 1024
    missing = StateChecks(required=declared, checks=actual.checks[:-1])
    assert missing.missing == (declared[-1],) and missing.status == "unknown"
