"""Separate read-only process reviewing original Shopping engineering facts."""

import os
from pathlib import Path
from admin_actor_review_live import review_actual_actor_attempt


def test_independent_actual_shopping_actor_attempt() -> None:
    review_actual_actor_attempt(
        Path(os.environ["LAB_SHOPPING_ACTOR_ATTEMPT_ROOT"]), shopping=True
    )
