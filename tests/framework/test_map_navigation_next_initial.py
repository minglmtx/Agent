"""The additional8 starts use the original passive wait and independent read rules."""

import json
from typing import Any
from urllib.parse import urlsplit
import pytest
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    EvidenceIntegrityError,
    OperationStopped,
)
from lab_generate_skill.domain.map_navigation_browser_initialization import (
    MapNavigationInitialization,
)
from lab_generate_skill.sites.map.navigation_browser_initialization import (
    MapNavigationBrowserInitializer,
)
from lab_generate_skill.sites.map.navigation_initial_readiness_rules import (
    original_navigation_readiness,
)
from lab_generate_skill.sites.map.navigation_initial_rules import (
    navigation_readiness_arguments,
)
from map_navigation_next_group_fixtures import ROWS, next_case, AdditionalStartPage
from map_navigation_browser_fixtures import Clock, CancelledControl
from test_core_contracts import reference
from test_slurm_commands import guard

EXTRA = tuple(
    r["source_task_id"]
    for r in ROWS
    if r["initial_branch"] not in ("plain_map", "communities")
)


def original(
    source: str,
) -> tuple[MapNavigationBrowserInitializer, AdditionalStartPage]:
    c = next_case(source)
    config = MapNavigationInitialization(
        endpoint="http://127.0.0.1:12001/",
        prepared_ref=reference("private", "prepared-task/1"),
        site_ref=reference("private", "site-resource-started/1"),
        native_contract_sha256=c.binding.native_contract.sha256,
    )
    clock = Clock()
    return MapNavigationBrowserInitializer(config, clock), AdditionalStartPage(clock)


@pytest.mark.parametrize("source", EXTRA)
def test_additional8_passive_exact_start_independent_read_and_no_renavigation(
    source: str,
) -> None:
    c = next_case(source)
    initial, page = original(source)
    initial.setup(page, c.public, guard())
    proof = initial.fact
    assert proof is not None
    original_navigation_readiness(proof, c.public)
    assert page.calls.count("goto:" + c.public.start_url) == 1
    assert proof.page.health.url == c.public.start_url
    if urlsplit(c.public.start_url).path == "/traces":
        assert (
            proof.native_signal_json is proof.native_view_json is None
            and proof.stable_seconds == 0
        )
    else:
        args = page.arguments
        assert (
            args is not None and args["expectedZoom"] is args["expectedCenter"] is None
        )
        assert args["search"] == (urlsplit(c.public.start_url).path == "/search")
        assert args["directions"] == (
            urlsplit(c.public.start_url).path == "/directions"
        )
        assert proof.stable_seconds >= 0.75
    with pytest.raises(InvalidTransition):
        initial.setup(page, c.public, guard())
    assert sum(v.startswith("goto:") for v in page.calls) == 1


@pytest.mark.parametrize(
    "fault",
    [
        "goto",
        "wait",
        "capture",
        "document-changed",
        "unknown-http",
        "loading",
        "cancel",
    ],
)
def test_partial_failed_or_cancelled_start_never_gets_ready_or_retries(
    fault: str,
) -> None:
    source = next(
        r["source_task_id"] for r in ROWS if r["initial_branch"] == "directions"
    )
    c = next_case(source)
    initial, page = original(source)
    page.fault = fault
    if fault == "unknown-http":
        page.status = None
    with pytest.raises(
        (ValueError, RuntimeError, OSError, TimeoutError, OperationStopped)
    ):
        initial.setup(
            page, c.public, CancelledControl() if fault == "cancel" else guard()
        )
    assert initial.fact is None and sum(v.startswith("goto:") for v in page.calls) <= 1
    if initial.attempted:
        with pytest.raises(InvalidTransition):
            initial.setup(page, c.public, guard())


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "loading",
        "wrong-native-range",
        "short-stable",
        "wrong-query",
        "wrong-controls",
        "empty-controls",
    ],
)
def test_independent_auto_pan_reader_rejects_incomplete_or_foreign_facts(
    fault: str,
) -> None:
    source = next(
        r["source_task_id"] for r in ROWS if r["initial_branch"] == "directions"
    )
    c = next_case(source)
    initial, page = original(source)
    initial.setup(page, c.public, guard())
    proof = initial.fact
    assert proof is not None and proof.native_signal_json is not None
    sig = json.loads(proof.native_signal_json)
    if fault == "missing":
        proof = proof.model_copy(update={"native_view_json": None})
    elif fault == "loading":
        sig["loading"] = True
        proof = proof.model_copy(update={"native_signal_json": json.dumps(sig)})
    elif fault == "wrong-native-range":
        sig["long"] = "/#map=12/0/0"
        proof = proof.model_copy(update={"native_signal_json": json.dumps(sig)})
    elif fault == "short-stable":
        proof = proof.model_copy(update={"stable_seconds": 0.1})
    elif fault == "wrong-query":
        proof = proof.model_copy(
            update={"start_url": c.public.start_url + "&foreign=1"}
        )
    elif fault == "empty-controls":
        sig["directionsFields"] = []
        proof = proof.model_copy(update={"native_signal_json": json.dumps(sig)})
    elif fault == "wrong-controls":
        sig["directionsFields"][0]["total"] = False
        proof = proof.model_copy(update={"native_signal_json": json.dumps(sig)})
    with pytest.raises((ValueError, EvidenceIntegrityError)):
        original_navigation_readiness(proof, c.public)


@pytest.mark.parametrize(
    "suffix",
    [
        "/directions#map=nan/0/0",
        "/search#map=12/91/0",
        "/search#map=12/0/0&map=12/0/0",
        "/other",
        "/#map=100/0/0",
        "/?query=other#map=12/0/0",
    ],
)
def test_bad_initial_range_rejected_before_navigation(suffix: str) -> None:
    c = next_case()
    task = c.public.model_copy(update={"start_url": "http://127.0.0.1:12001" + suffix})
    with pytest.raises(ValueError):
        navigation_readiness_arguments(task)
