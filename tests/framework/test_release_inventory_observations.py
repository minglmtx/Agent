"""Inventory reuses one checked stat observation; later calls remain fresh."""

from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from lab_generate_skill.adapters.releases.files import _inventory
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from test_slurm_commands import guard


def test_one_lstat_per_entry_and_fresh_inventory_on_each_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "tree"
    directory.mkdir()
    (directory / "nested").mkdir()
    (directory / "one").write_bytes(b"one")
    (directory / "nested/two").write_bytes(b"two")
    for path in (directory / "nested", directory):
        path.chmod(0o555)
    original = Path.lstat
    observations: Counter[Path] = Counter()

    def counted(path: Path, *args: Any, **kwargs: Any) -> Any:
        observations[path] += 1
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", counted)
    first = _inventory(directory, guard(30))
    assert set(first) == {"one", "nested/two"}
    assert observations == {
        directory / "nested": 1,
        directory / "one": 1,
        directory / "nested/two": 1,
    }
    observations.clear()
    assert _inventory(directory, guard(30)) == first
    assert all(value == 1 for value in observations.values())


@pytest.mark.parametrize("kind", ("link", "fifo", "writable"))
def test_single_observation_keeps_unsafe_entry_and_mode_rejection(
    tmp_path: Path, kind: str
) -> None:
    import os

    if kind == "link":
        (tmp_path / "bad").symlink_to("missing")
    elif kind == "fifo":
        os.mkfifo(tmp_path / "bad")
    else:
        (tmp_path / "nested").mkdir()
    tmp_path.chmod(0o555)
    with pytest.raises(EvidenceIntegrityError):
        _inventory(tmp_path, guard(30))
