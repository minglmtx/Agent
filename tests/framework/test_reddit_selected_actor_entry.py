"""Wrong source cannot allocate an Actor or be silently discarded by another site."""

from pathlib import Path
from typing import Any
import pytest
from admin_actor_live import run_actual_actor_business_chain
from reddit_source_selection import RedditSourceSelection
from reddit_forum_source_fixtures import CONTRACT, public


@pytest.mark.parametrize("site", ["shopping_admin", "shopping", "gitlab", "map"])
def test_selected_reddit_input_refuses_foreign_actor_entry_before_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, site: Any
) -> None:
    selection = RedditSourceSelection(CONTRACT.read_bytes(), public())
    absent: Any = None
    with pytest.raises(ValueError):
        run_actual_actor_business_chain(
            absent, tmp_path, monkeypatch, site_id=site, reddit_selection=selection
        )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("value", [{}, "selection", 1])
def test_actor_entry_requires_validated_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: Any
) -> None:
    absent: Any = None
    with pytest.raises(ValueError):
        run_actual_actor_business_chain(
            absent, tmp_path, monkeypatch, site_id="reddit", reddit_selection=value
        )
    assert list(tmp_path.iterdir()) == []
