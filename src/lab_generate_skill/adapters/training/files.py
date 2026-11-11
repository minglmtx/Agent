"""Original atomic run/checkpoint metadata helpers; worker-internal filesystem I/O."""

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def latest_checkpoint(output_dir: Path) -> Path | None:
    candidates: list[tuple[int, Path]] = []
    for path in output_dir.glob("checkpoint-*"):
        try:
            step = int(path.name.rsplit("-", 1)[-1])
        except ValueError:
            continue
        if (path / "complete.json").exists():
            candidates.append((step, path))
    return max(candidates, default=(0, None))[1]


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def check_run_contract(
    output_dir: Path, contract: dict[str, Any], resume: bool
) -> None:
    manifest = output_dir / "run_manifest.json"
    if manifest.exists():
        if json.loads(manifest.read_text()) != contract:
            raise ValueError(
                "Training data, model or hyperparameters changed; use a new output directory"
            )
        if not resume:
            raise ValueError("Existing run requires --resume or a new output directory")
    elif output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("Nonempty output directory without training manifest")
    else:
        atomic_json(manifest, contract)
