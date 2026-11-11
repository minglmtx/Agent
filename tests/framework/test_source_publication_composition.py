"""All three original source bindings publish only after recovery and close.

Native/page/kernel doubles remain the original declared fixture premises. This
tests the budget join, without a real source, Actor, or training permission.
"""

from pathlib import Path
from typing import Any
import pytest

from test_admin_navigation_source_composition import original_source_unit_case
from gitlab_group_source_fixtures import group_source_unit_case
from test_gitlab_group_source_composition import contracts_for
from test_source_recovery_budget_consumers import (
    source_case as source_case,
    contracts as contracts,
    node_path as node_path,
)
from test_map_source_qualification import (
    test_source_initializer_unique_initial_observation_restore_reset_and_close_before_publication as map_case,
)
from map_registered_worker_fixtures import RegisteredMapCase
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.bootstrap.source_browser_assets import SourceBrowserAssets


def test_map_closed_publication_uses_original_root_after_acquisition_expiry(
    source_case: tuple[
        RegisteredMapCase, OriginalSourceQualificationOwner, SourceBrowserAssets
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    map_case(
        source_case,
        monkeypatch,
        False,
        False,
        use_publication_root=True,
        expire_acquisition=True,
    )


@pytest.mark.parametrize("site", ["admin", "group"])
@pytest.mark.parametrize(
    "fault", ["none", "acquisition_expired_after_reset", "restore_return_lost"]
)
def test_closed_publication_root_does_not_skip_reset_or_close(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    site: str,
    fault: str,
) -> None:
    if site == "admin":
        result = original_source_unit_case(
            tmp_path,
            node_path,
            monkeypatch,
            contracts,
            fault,
            use_publication_root=True,
        )
    else:
        import gitlab_group_fixtures as inputs
        from test_gitlab_group_complete_starts import W

        source = "286d4ac488bdcd446ffc"
        monkeypatch.setattr(
            inputs,
            "FIXTURE",
            W
            / "experiments/sft-ordinary-source-bindings-v1/prepared/contracts"
            / (source + ".json"),
        )
        result = group_source_unit_case(
            tmp_path,
            node_path,
            monkeypatch,
            contracts_for(source),
            fault,
            use_publication_root=True,
        )
    if fault == "restore_return_lost":
        assert result.facts is None and result.qualified is None
    else:
        assert result.facts.reset.status == "safe" and result.qualified is not None
