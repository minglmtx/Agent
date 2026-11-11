"""Existing generic capture on real local records/Actor/owner; no live grant."""

from pathlib import Path
from typing import Any
import pytest
from shopping_category_task_capture_fixtures import capture_case
from test_shopping_category_navigation_input import originals as originals
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize("heading", ["Electronics", ""])
def test_original_generic_capture_closes_browser_and_scores_complete_result(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    heading: str,
) -> None:
    c = capture_case(
        tmp_path,
        node_path,
        monkeypatch,
        (originals[0][0], originals[0][2]),
        heading=heading,
        fault="none",
    )
    assert c["capture"].state.phase == "captured"


@pytest.mark.parametrize(
    "fault",
    [
        "task-denied",
        "page-denied",
        "page-write",
        "terminal-write",
        "close-denied",
        "guard-denied",
        "guard-write",
        "selection-write",
        "cancel",
    ],
)
def test_generic_category_partial_failures_keep_original_owner_and_never_replay(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    fault: str,
) -> None:
    c = capture_case(
        tmp_path,
        node_path,
        monkeypatch,
        (originals[0][0], originals[0][2]),
        heading="Electronics",
        fault=fault,
    )
    assert c["capture"].state.phase == "quarantined"
