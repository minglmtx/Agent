"""Small mutable input tree with explicit byte pins, no external assets."""

import hashlib
from pathlib import Path

from lab_generate_skill.domain.release import ReleaseArtifact, ReleaseFile
from lab_generate_skill.adapters.releases.artifact_freeze import FileArtifactFreezer


def fixture(root: Path) -> tuple[FileArtifactFreezer, ReleaseArtifact]:
    source = root / "source"
    source.mkdir()
    (source / "nested").mkdir()
    (root / "published").mkdir()
    files = []
    for name, data, executable in (
        ("empty", b"", False),
        ("nested/data.bin", b"source-data", False),
        ("run.sh", b"echo unit\n", True),
    ):
        path = source / name
        path.write_bytes(data)
        path.chmod(0o755 if executable else 0o644)
        files.append(
            ReleaseFile(
                path=name,
                size_bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                executable=executable,
            )
        )
    return FileArtifactFreezer(root, root / "published"), ReleaseArtifact(
        artifact_id="input", root=str(source), files=tuple(files)
    )
