"""Cheap syntax and persisted-record checks before expensive installed workers."""

import ast
from pathlib import Path
import pytest
from installed_claim_fixtures import setup
from installed_source_fixtures import InstalledFixture
from release_fixtures import manifest
from lab_generate_skill.adapters.storage.atomic_snapshot import AtomicSnapshotFile
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "filename,names",
    [
        ("test_claim_installed.py", ("BLOCKED",)),
        ("test_publication_blocking.py", ("BLOCKED", "CONTROLLER")),
        ("test_publication_installed.py", ("CLOSE_FAULT",)),
    ],
)
def test_injection_scripts_compile_without_starting_processes(
    filename: str, names: tuple[str, ...]
) -> None:
    tree = ast.parse(Path(__file__).with_name(filename).read_text())
    scripts = {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    for name in names:
        compile(scripts[name], f"{filename}:{name}", "exec")


def test_claim_fixture_contains_readable_initialization_and_stable_lock(
    tmp_path: Path,
) -> None:
    fixture = InstalledFixture(
        tmp_path / "python", tmp_path, manifest(tmp_path / "code")
    )
    _, record, command = setup(tmp_path, fixture)
    root = Path(command.root)
    name = record.binding.key.filename
    assert (root / (name + ".initialized")).is_file()
    lock = root / (name + ".lock")
    identity = lock.stat().st_ino
    with AtomicSnapshotFile(root, name, max_bytes=128 * 1024).locked(
        guard(10), create_lock=False
    ) as transaction:
        assert transaction.read() == record.model_dump_json().encode()
    assert lock.stat().st_ino == identity
