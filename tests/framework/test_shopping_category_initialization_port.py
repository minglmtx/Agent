"""Full category initializer consumes original envelopes; upstream rights unit-only."""

from pathlib import Path
from typing import Any
import pytest
from shopping_category_initialization_port_fixtures import initialization_case
from test_shopping_category_navigation_input import originals as originals
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "capture-denied",
        "initial-write",
        "cancel-after-capture",
        "comparison-denied",
        "final-admission-denied",
    ],
)
def test_category_whole_initializer_and_original_close(
    node_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    fault: str,
) -> None:
    facts = initialization_case(tmp_path, node_path, monkeypatch, originals[0], fault)
    assert facts["closed"] and facts["source_attempt"] != facts["candidate_attempt"]
    if fault == "none":
        assert facts["result"].actor.task.identity == originals[0][2].identity
        assert facts["body_admission_count"] == 5
    else:
        assert facts["primary"] in ("PermissionError", "OperationStopped", "OSError")
        if fault == "final-admission-denied":
            assert facts["body_admission_count"] == 5
