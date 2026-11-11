"""Original Postmill initialization/unique observation/full reset; no Actor/model."""

import json
import os
from pathlib import Path
import pytest
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from storage_installation_fixtures import storage_installation
from reddit_initialization_fixture import source_hooks
from test_site_resource_installed import run_registered_site_case
from reddit_source_selection import RedditSourceSelection
from lab_generate_skill.domain.baseline import BaselineInputs
from lab_generate_skill.domain.evidence import EvidenceRef
from test_slurm_commands import guard


def test_actual_registered_reddit_initialization_observation_and_reset(
    installed_sources: InstalledFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_initialization(installed_sources, tmp_path, monkeypatch)


def run_initialization(
    installed_sources: InstalledFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    selection: RedditSourceSelection | None = None,
) -> None:
    hooks = source_hooks(
        tmp_path,
        storage_installation(installed_sources),
        os.environ["SLURM_JOB_ID"],
        selection=selection,
    )
    run_registered_site_case(
        installed_sources,
        tmp_path,
        monkeypatch,
        "qualified_source",
        site_id="reddit",
        task_hooks=hooks,
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

    if selection is not None:
        ref = EvidenceRef.model_validate(
            facts["prepared_browser"]["baseline_inputs_ref"]
        )
        original = BaselineInputs.model_validate_json(
            hooks.evidence.read(ref, control=guard(30))
        )
        assert original.public_task.identity == selection.public_template.identity
        assert original.public_task.goal == selection.public_template.goal
        assert original.public_task.start_url.endswith("/forums/all")
        assert original.prepared.private_checks_ref == original.binding.private_spec_ref
