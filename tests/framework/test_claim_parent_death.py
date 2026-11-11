"""Same native parent-death contract, exercised against the actual claim leaf."""

from pathlib import Path
import pytest
import test_publication_blocking as scenario
from test_claim_installed import BLOCKED
from installed_claim_fixtures import setup
from lab_generate_skill.adapters.storage.claim_protocol import encode_claim_command
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)


def test_original_controller_exit_stops_claim_reader(
    tmp_path: Path, installed_sources: InstalledFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scenario, "setup", setup)
    monkeypatch.setattr(scenario, "BLOCKED", BLOCKED)
    monkeypatch.setattr(scenario, "encode_publication_command", encode_claim_command)
    monkeypatch.setattr(
        scenario,
        "CONTROLLER",
        scenario.CONTROLLER.replace("publication_protocol", "claim_protocol").replace(
            "publication_command", "claim_command"
        ),
    )
    scenario.test_parent_exit_stops_native_reader(tmp_path, installed_sources)
