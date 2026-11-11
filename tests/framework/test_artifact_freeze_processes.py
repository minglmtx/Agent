"""Two same-node publishers cannot overwrite the same destination directory."""

import multiprocessing
from pathlib import Path
from typing import Any

from lab_generate_skill.adapters.releases.artifact_freeze import FileArtifactFreezer
from lab_generate_skill.domain.release import ReleaseArtifact
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from artifact_freeze_fixtures import fixture
from test_slurm_commands import guard


def worker(workspace: str, raw: str, barrier: Any, queue: Any) -> None:
    root = Path(workspace)
    source = ReleaseArtifact.model_validate_json(raw)
    barrier.wait(timeout=20)
    try:
        result = FileArtifactFreezer(root, root / "published").freeze(
            source, "v1", guard()
        )
        queue.put(("verified", Path(result.root).stat().st_ino))
    except (FileExistsError, EvidenceIntegrityError):
        queue.put(("not_verified", None))


def test_same_target_competition_preserves_one_complete_artifact(
    tmp_path: Path,
) -> None:
    freezer, source = fixture(tmp_path)
    context = multiprocessing.get_context("spawn")
    barrier, queue = context.Barrier(2), context.Queue()
    workers = [
        context.Process(
            target=worker,
            args=(str(tmp_path), source.model_dump_json(), barrier, queue),
        )
        for _ in range(2)
    ]
    try:
        for process in workers:
            process.start()
        for process in workers:
            process.join(timeout=30)
            assert process.exitcode == 0
        results = [queue.get(timeout=5) for _ in workers]
        verified = {inode for state, inode in results if state == "verified"}
        assert len(verified) == 1
        result = freezer.freeze(source, "v1", guard())
        assert Path(result.root).stat().st_ino in verified
        assert list((tmp_path / "published").iterdir()) == [Path(result.root)]
    finally:
        for process in workers:
            if process.is_alive():
                process.kill()
                process.join(timeout=5)
        queue.close()
