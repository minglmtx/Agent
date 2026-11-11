"""Complete42 exact source and original semantics; no live execution qualification."""

import hashlib
import json
import re
from typing import Any
import pytest
from lab_generate_skill.bootstrap.map_navigation_source import (
    MapNavigationSourceSelection,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.map_navigation_next_group import (
    NEXT_NAVIGATION_PAGE_GROUP,
    NEXT_NAVIGATION_PAGE_PINS,
)
from lab_generate_skill.domain.map_navigation_scope import (
    NAVIGATION_PAGE_MEMBERS,
    check_page_navigation_scope,
)
from lab_generate_skill.sites.map.tasks.navigation_policy import navigation_initial_spec
from lab_generate_skill.sites.map.navigation_rules import (
    navigation_outcome,
    original_completion,
)
from map_navigation_fixtures import ORIGIN, navigation_case, reference
from map_navigation_next_group_fixtures import ROWS, SOURCES, next_case, selected
from map_navigation_source_selection import (
    MapNavigationSourceSelection as CompatibilitySelection,
)
from test_map_navigation_original_semantics import (
    evaluate_navigation,
    guard_site_result,
)


@pytest.mark.parametrize("source", SOURCES)
def test_complete_next_group_original_source_scope_and_semantics(source: str) -> None:
    c = next_case(source)
    selection = selected(source)
    assert type(selection) is CompatibilitySelection is MapNavigationSourceSelection
    assert NEXT_NAVIGATION_PAGE_PINS[source] == (
        c.public.identity.task_id,
        hashlib.sha256(c.raw).hexdigest(),
    )
    check_page_navigation_scope(c.public.identity, reference(c.raw).sha256)
    spec = selection.load(reference(c.raw), c.public)
    assert selection == selected(
        source
    )  # Pure repeated loading performs no native operation.
    assert selection.public_at(ORIGIN + "/", None) == c.public
    assert spec.task.task_id == spec.task.source_task_id == spec.binding.runtime_task_id
    assert spec.goal_revision is None and spec.admission == "unverified"
    assert original_completion(spec.completion) == c.native["completion"]
    assert (
        spec.completion.map_route is None and c.native["eligible_for_training"] is False
    )
    assert (
        navigation_initial_spec(c.public.identity, reference(c.raw).sha256).task
        == c.public.identity
    )
    public = json.loads(c.public.model_dump_json())
    assert public["goal"] == c.native["goal"]
    assert all(
        k not in public for k in ("completion", "admission", "native_contract_ref")
    )
    heading = re.sub(r"\\(.)", r"\1", c.native["completion"]["heading_regex"][1:-1])
    page = dict(
        url=ORIGIN + c.native["control_target_path"],
        http_status=200,
        title="OpenStreetMap",
        heading_texts=[heading],
        login_page=False,
        error_page=False,
    )
    for fault in (
        "none",
        "wrong-path",
        "wrong-heading",
        "missing",
        "server",
        "runtime",
        "protected",
    ):
        current: dict[str, Any] = dict(page)
        if fault == "wrong-path":
            current["url"] = ORIGIN + c.native["wrong_target_path"]
        elif fault == "wrong-heading":
            current["heading_texts"] = ["A different object"]
        elif fault == "missing":
            current.pop("heading_texts")
        elif fault == "server":
            current["http_status"] = 503
        error = {"error": "original action unconfirmed"} if fault == "runtime" else None
        expected = guard_site_result(
            evaluate_navigation(c.native, current, site_origin=ORIGIN),
            runtime_error=error,
            selected_records_unchanged=fault != "protected",
        )
        actual = navigation_outcome(
            spec,
            current,
            site_origin=ORIGIN,
            runtime_error=error is not None,
            selected_records_unchanged=fault != "protected",
        )
        assert actual.original_result() == expected
        assert actual.status == (
            "success"
            if fault == "none"
            else "failure" if fault in ("wrong-path", "wrong-heading") else "unknown"
        )


def test_complete_group_is_exact_not_sampled_or_training_qualification() -> None:
    assert len(ROWS) == len(SOURCES) == len(set(SOURCES)) == 42
    assert set(SOURCES) == set(NEXT_NAVIGATION_PAGE_PINS)
    assert all(
        r["effective_batch_id"] == NEXT_NAVIGATION_PAGE_GROUP and r["split"] == "train"
        for r in ROWS
    )
    assert all(
        r["training_eligible"] is False
        and r["multiple_candidates_required_for_current_group"] is False
        for r in ROWS
    )
    assert (
        len(NAVIGATION_PAGE_MEMBERS) == 50
        and "058c211ed6572633b8e3" not in NAVIGATION_PAGE_MEMBERS
    )
    assert {r["initial_branch"] for r in ROWS} == {
        "plain_map",
        "communities",
        "directions",
        "search",
        "traces",
    }


@pytest.mark.parametrize(
    "fault", ["pin", "task", "source", "split", "version", "family"]
)
def test_new_group_rejects_wrong_original_binding_before_native_effect(
    fault: str,
) -> None:
    c = next_case()
    identity = c.public.identity
    pin = reference(c.raw).sha256
    if fault == "pin":
        pin = "0" * 64
    else:
        identity = identity.model_copy(
            update={
                {
                    "task": "task_id",
                    "source": "source_task_id",
                    "split": "split",
                    "version": "contract_version",
                    "family": "family",
                }[fault]: {
                    "task": "other",
                    "source": "other",
                    "split": "test",
                    "version": 2,
                    "family": "other",
                }[
                    fault
                ]
            }
        )
    with pytest.raises(ValueError):
        check_page_navigation_scope(identity, pin)


@pytest.mark.parametrize(
    "raw", [None, "", 1, [], b"", b"{}", b"[]", b" " * (1024**2 + 1)]
)
def test_source_contract_empty_wrong_type_or_extreme_is_refused(raw: Any) -> None:
    c = next_case()
    with pytest.raises((TypeError, ValueError, EvidenceIntegrityError)):
        MapNavigationSourceSelection(raw, c.binding, c.public)


def test_original8_and_route_boundary_preserved() -> None:
    old = navigation_case("0189de83adbd18ca5109")
    check_page_navigation_scope(old.public.identity, reference(old.raw).sha256)
    with pytest.raises(ValueError):
        route = navigation_case("058c211ed6572633b8e3")
        check_page_navigation_scope(route.public.identity, reference(route.raw).sha256)
