"""Selected fourth website on the original registered Actor/browser/site driver."""

from pathlib import Path
import pytest
from admin_actor_live import run_actual_actor_business_chain
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)


def test_actual_reddit_actor_business_chain(
    installed_sources: InstalledFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_actual_actor_business_chain(
        installed_sources, tmp_path, monkeypatch, site_id="reddit"
    )
