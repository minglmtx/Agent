"""Exact public starts including queries/fragments, no forced ETA login/actions."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.browser_initialization import browser_initializer
from lab_generate_skill.domain.shopping_navigation_browser_initialization import (
    ShoppingCategoryInitialization,
)
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    InvalidTransition,
    OperationStopped,
)
from lab_generate_skill.sites.shopping.navigation_browser_initialization import (
    ShoppingCategoryBrowserInitializer,
)
from shopping_category_browser_fixtures import browser_configuration, Page
from test_shopping_category_navigation_input import originals as originals
from test_slurm_commands import guard


def test_all18_same_original_start_factory_single_navigation_and_repeat(
    originals: Any,
) -> None:
    for raw, _, public in originals:
        config = browser_configuration(raw, public)
        selected = browser_initializer(config)
        assert isinstance(selected, ShoppingCategoryBrowserInitializer)
        page = Page(public)
        selected.setup(page, public, guard())
        assert page.visits == [public.start_url] and len(page.handlers) == 1
        with pytest.raises(InvalidTransition):
            selected.setup(page, public, guard())
        assert page.visits == [public.start_url]


@pytest.mark.parametrize(
    "fault",
    [
        "wrong_start",
        "foreign_task",
        "first_document",
        "login",
        "error",
        "status_missing",
        "loading",
        "cancel",
        "after_navigation",
    ],
)
def test_setup_boundary_and_partial_failure_does_not_repeat(
    originals: Any, fault: str
) -> None:
    raw, _, public = originals[0]
    config = browser_configuration(raw, public)
    selected = browser_initializer(config)
    page = Page(public)
    if fault == "wrong_start":
        page.health["url"] = public.start_url + "&foreign=1"
    if fault == "foreign_task":
        public = public.model_copy(
            update={
                "identity": public.identity.model_copy(
                    update={"family": "recorded_order_eta"}
                )
            }
        )
    if fault == "first_document":
        page.url = public.start_url
    if fault == "login":
        page.health["login_page"] = True
    if fault == "error":
        page.health.update(http_status=503, title="Service unavailable")
    if fault == "status_missing":
        page.health.update(http_status=None, status_source="unavailable")
    if fault == "loading":
        page.ready = "loading"
    if fault == "after_navigation":
        page.failure = True

    class Cancel:
        def checkpoint(self) -> float:
            raise OperationStopped("CANCELLED", "category-browser-setup")

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises((ValueError, OwnershipConflict, OperationStopped, TimeoutError)):
        selected.setup(page, public, Cancel() if fault == "cancel" else guard())
    if fault in ("foreign_task", "first_document", "cancel"):
        assert not page.visits
    else:
        assert len(page.visits) == 1
        with pytest.raises(InvalidTransition):
            selected.setup(page, public, guard())
        assert len(page.visits) == 1


@pytest.mark.parametrize(
    "change", ["endpoint", "kind", "family", "prepared", "site", "hash"]
)
def test_explicit_kind_refs_family_and_origin_are_checked_before_factory(
    originals: Any, change: str
) -> None:
    raw, _, public = originals[0]
    data = browser_configuration(raw, public).model_dump(mode="json")
    if change == "endpoint":
        data["initialization"]["endpoint"] = "http://outside.invalid/"
    if change == "kind":
        data["initialization"] = {"kind": "public_navigation"}
    if change == "family":
        data["spec"]["task"]["identity"]["family"] = "recorded_order_eta"
    if change in ("prepared", "site"):
        data["initialization"][change + "_ref"]["visibility"] = "public"
    if change == "hash":
        data["initialization"]["native_contract_sha256"] = ""
    with pytest.raises(ValueError):
        BrowserWorkerConfiguration.model_validate(data)


@pytest.mark.parametrize("invalid", [None, "", {}, [], False])
def test_wrong_initialization_types_refused(invalid: Any) -> None:
    with pytest.raises(ValueError):
        ShoppingCategoryInitialization.model_validate(invalid)
