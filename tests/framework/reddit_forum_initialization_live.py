"""New source's original forums start through the existing registered entry; no Actor."""

from pathlib import Path
import pytest
from reddit_initialization_live import run_initialization
from reddit_source_selection import RedditSourceSelection
from reddit_forum_source_fixtures import CONTRACT, public
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker


def test_actual_selected_forum_initialization_observation_and_full_reset(
    installed_sources: InstalledFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_initialization(
        installed_sources,
        tmp_path,
        monkeypatch,
        selection=RedditSourceSelection(CONTRACT.read_bytes(), public()),
    )
