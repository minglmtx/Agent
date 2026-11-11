"""Offline test artifact commands; credentials and source paths are excluded."""

import os
from pathlib import Path
import subprocess


def checked_command(argv: list[str], *, cwd: Path) -> bytes:
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "PYTHONPATH",
            "PYTHONHOME",
            "OPENROUTER_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
        )
    }
    completed = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, timeout=90)
    if completed.returncode:
        raise RuntimeError(
            completed.stdout.decode(errors="replace")
            + completed.stderr.decode(errors="replace")
        )
    return completed.stdout
