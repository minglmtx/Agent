"""One selected private Group engineering task on the current shared Actor chain."""

import os
from pathlib import Path
import pytest
from admin_actor_live import run_actual_actor_business_chain
from admin_actor_review_live import review_actual_actor_attempt
from gitlab_source_selection import GitlabSourceSelection, group_selection
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)

SOURCE = "e4d658cfba6588f6a386"
CONTRACT_SHA = "acd7e87bdbfbe2d18d093135bcbb1940d7cf259a13d7665511be8bc3437ce750"


def selected_group() -> GitlabSourceSelection:
    selected = group_selection()
    if not isinstance(selected, GitlabSourceSelection):
        raise TypeError("Explicit validated selected Group input required")
    identity = selected.public_template.identity
    if (
        not selected.group
        or (identity.source_task_id, identity.task_id) != (SOURCE, SOURCE)
        or selected.reference().sha256 != CONTRACT_SHA
    ):
        raise ValueError("Only the frozen original selected Group source is in scope")
    return selected


def test_actual_private_group_actor_business_chain(
    installed_sources: InstalledFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = selected_group()
    run_actual_actor_business_chain(
        installed_sources,
        tmp_path,
        monkeypatch,
        site_id="gitlab",
        gitlab_selection=selected,
    )


def test_independent_actual_private_group_actor_attempt() -> None:
    selected = selected_group()
    review_actual_actor_attempt(
        Path(os.environ["LAB_GROUP_ACTOR_ATTEMPT_ROOT"]),
        gitlab=True,
        expected_identity=selected.public_template.identity,
    )
