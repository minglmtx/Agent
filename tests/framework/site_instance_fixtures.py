"""Node-local test roots independent of the checker's workspace TMPDIR."""

from collections.abc import Iterator
from pathlib import Path
import tempfile
import pytest


@pytest.fixture
def node_path() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="lab-site-unit-", dir="/tmp") as directory:
        yield Path(directory)
