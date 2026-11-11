"""Separate process reviewing the original GitLab attempt; no site/model calls."""

import os
from pathlib import Path
from admin_actor_review_live import review_actual_actor_attempt


def test_independent_actual_gitlab_actor_attempt() -> None:
    review_actual_actor_attempt(
        Path(os.environ["LAB_GITLAB_ACTOR_ATTEMPT_ROOT"]), gitlab=True
    )
