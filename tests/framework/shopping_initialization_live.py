"""Selected fresh Shopping initialization/unique Observation/reset, no Actor."""

import json
import os
from pathlib import Path
import pytest
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from test_site_resource_installed import run_registered_site_case


def test_actual_registered_shopping_initialization_observation_and_reset(
    installed_sources: InstalledFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_registered_site_case(
        installed_sources, tmp_path, monkeypatch, "qualified_source", site_id="shopping"
    )
    facts = json.loads(
        (
            Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
            / "registered-site-qualified_source.json"
        ).read_text()
    )
    assert facts["passed"] and facts["private_root_removed"]
    assert facts["prepared_browser"][
        "original_browser_domain_closed_before_site_restore"
    ]
    assert facts["whole_tree_restored_before_resume"]
    assert facts["qualified_source"]["public_context_ref"]
