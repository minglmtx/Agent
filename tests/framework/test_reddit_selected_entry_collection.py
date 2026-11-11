"""Selected native entry collection must not initialize website/browser/model."""

import os
import subprocess
import sys
from pathlib import Path


def test_selected_and_original_native_entries_are_inert_on_collection() -> None:
    project = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/framework/reddit_initialization_live.py",
            "tests/framework/reddit_forum_initialization_live.py",
            "tests/framework/reddit_forum_actor_live.py",
            "tests/framework/reddit_actor_review_live.py",
        ],
        cwd=project,
        env=dict(os.environ),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "4 tests collected" in result.stdout
