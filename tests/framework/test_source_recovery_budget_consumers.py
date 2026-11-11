"""The same explicit recovery profile through original Map/Admin producers.

SQL/services/page/kernel/rights remain the original explicit fixture premises;
no actual source claim, live website/model or training qualification is granted.
"""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.bootstrap.source_browser_assets import SourceBrowserAssets
from map_registered_worker_fixtures import RegisteredMapCase
from test_map_source_qualification import source_case as source_case
from test_map_source_qualification import (
    test_source_initializer_unique_initial_observation_restore_reset_and_close_before_publication as map_original,
)
from test_admin_navigation_source_composition import original_source_unit_case
from test_admin_navigation_input import contracts as contracts
from test_source_recovery_budgets import profile
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize(
    "cancel_after_reset,lose_restore_return",
    [(False, False), (True, False), (False, True)],
)
def test_explicit_map_source_profile_keeps_original_once_restore_and_cancellation(
    source_case: tuple[
        RegisteredMapCase, OriginalSourceQualificationOwner, SourceBrowserAssets
    ],
    monkeypatch: pytest.MonkeyPatch,
    cancel_after_reset: bool,
    lose_restore_return: bool,
) -> None:
    map_original(
        source_case,
        monkeypatch,
        cancel_after_reset,
        lose_restore_return,
        recovery_budgets=profile(),
    )


@pytest.mark.parametrize("fault", ["none", "cancel_after_reset", "restore_return_lost"])
def test_explicit_admin_source_profile_keeps_original_once_restore_and_cancellation(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    fault: str,
) -> None:
    result = original_source_unit_case(
        tmp_path, node_path, monkeypatch, contracts, fault, recovery_budgets=profile()
    )
    if fault == "none":
        assert result.qualified is not None and result.facts.reset.status == "safe"
    else:
        assert result.qualified is None and result.facts is None
