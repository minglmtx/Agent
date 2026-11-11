"""Separate process reviewing the original Reddit attempt; no site/model calls."""

import os
from pathlib import Path
from admin_actor_review_live import review_actual_actor_attempt
from generator_engine_live import verify_source


def test_independent_actual_reddit_actor_attempt() -> None:
    reviewer = Path(__file__).resolve().parents[2]
    receipt = Path(os.environ["LAB_REVIEWER_SOFTWARE_RECEIPT"])
    verify_source(receipt, source_root=reviewer)
    review_actual_actor_attempt(
        Path(os.environ["LAB_REDDIT_ACTOR_ATTEMPT_ROOT"]),
        reddit=True,
        execution_source_root=Path(os.environ["LAB_REVIEW_ORIGINAL_SOURCE_ROOT"]),
    )
    verify_source(receipt, source_root=reviewer)
