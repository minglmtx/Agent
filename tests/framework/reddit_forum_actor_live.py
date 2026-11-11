"""First Actor for the distinct original forums source, never the old unknown task."""

from pathlib import Path
import pytest
from admin_actor_live import run_actual_actor_business_chain
from reddit_source_selection import RedditSourceSelection
from reddit_forum_source_fixtures import CONTRACT, public
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker


def test_actual_selected_forum_actor_business_chain(
    installed_sources: InstalledFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_actual_actor_business_chain(
        installed_sources,
        tmp_path,
        monkeypatch,
        site_id="reddit",
        reddit_selection=RedditSourceSelection(CONTRACT.read_bytes(), public()),
    )
