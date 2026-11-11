"""Explicit source recovery config, original ports and cancellation/unknown paths."""

from datetime import datetime, timezone
from inspect import signature
from pathlib import Path
from typing import Any, get_args
import pytest
from lab_generate_skill.domain.source_recovery_budget import (
    SourceRecoveryBudgets,
    RecoveryStage,
    recovery_seconds,
)
from lab_generate_skill.bootstrap.map_source_qualification import (
    qualify_map_navigation_source,
)
from lab_generate_skill.bootstrap.admin_navigation_source_qualification import (
    qualify_admin_navigation_source,
)
from lab_generate_skill.bootstrap.gitlab_group_source_qualification import (
    qualify_group_source,
)
from lab_generate_skill.bootstrap.gitlab_group_source import GROUP_NATIVE_PINS
from gitlab_group_source_fixtures import group_source_unit_case
from test_gitlab_group_source_composition import contracts_for
from test_gitlab_group_complete_starts import W
from site_instance_fixtures import node_path as node_path


def profile() -> SourceRecoveryBudgets:
    return SourceRecoveryBudgets(
        preparation_metadata_seconds=90,
        browser_close_seconds=90,
        restore_seconds=90,
        resume_seconds=90,
        reset_facts_seconds=90,
        site_close_seconds=90,
    )


@pytest.mark.parametrize("stage", get_args(RecoveryStage))
@pytest.mark.parametrize("bad", [None, 0, -1, True, "90", {}, [], 3601])
def test_invalid_recovery_values_are_rejected_at_config_boundary(
    stage: str, bad: Any
) -> None:
    with pytest.raises(ValueError):
        SourceRecoveryBudgets.model_validate({**profile().model_dump(), stage: bad})


def test_exact_profiles_and_legacy_branch_are_separate_and_nested_close_is_not_added_twice() -> (
    None
):
    p = profile()
    assert SourceRecoveryBudgets.model_validate_json(p.model_dump_json()) == p
    assert p.complete_recovery_path_seconds == 450
    for stage in get_args(RecoveryStage):
        assert recovery_seconds(p, stage, 1800) == 90
        assert recovery_seconds(None, stage, 1800) == 1800
    for bad in (
        {},
        {**p.model_dump(), "schema_version": "source-recovery-budgets/99"},
        {**p.model_dump(), "extra": 1},
    ):
        with pytest.raises(ValueError):
            SourceRecoveryBudgets.model_validate(bad)


@pytest.mark.parametrize(
    "factory",
    [
        qualify_map_navigation_source,
        qualify_admin_navigation_source,
        qualify_group_source,
    ],
)
def test_illegal_model_copy_revalidated_before_any_source_or_resource(
    factory: Any,
) -> None:
    bad = profile().model_copy(update={"browser_close_seconds": 0})
    # Complete source objects are deliberately absent. Budget validation
    # precedes source/CAS/website acquisition, so no fake owner is supplied.
    kwargs: dict[str, Any] = {
        name: None
        for name, p in signature(factory).parameters.items()
        if p.default is p.empty
    }
    kwargs["recovery_budgets"] = bad
    with pytest.raises(ValueError):
        factory(**kwargs)


@pytest.mark.parametrize("fault", ["none", "cancel_after_reset", "restore_return_lost"])
def test_explicit_source_budget_reaches_original_browser_close_restore_and_unknown_exit(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    import gitlab_group_fixtures as inputs

    source = next(iter(GROUP_NATIVE_PINS))
    monkeypatch.setattr(
        inputs,
        "FIXTURE",
        W
        / "experiments/sft-ordinary-source-bindings-v1/prepared/contracts"
        / (source + ".json"),
    )
    budget = profile()
    c = group_source_unit_case(
        tmp_path,
        node_path,
        monkeypatch,
        contracts_for(source),
        fault,
        recovery_budgets=budget,
    )
    if fault == "none":
        assert c.qualified is not None and c.facts.reset.status == "safe"
        now = datetime.now(timezone.utc)
        for record in (c.facts.browser_record, c.facts.site_record):
            assert record.state == "closed"
            remaining = (record.events[-1].operation.deadline - now).total_seconds()
            assert 0 < remaining <= 90
    else:
        assert c.qualified is None and c.facts is None
