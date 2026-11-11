"""Read the migrated model's exact existing inventory for engineering GPU checks."""

import hashlib
import json
from pathlib import Path
from lab_generate_skill.domain.release import ReleaseArtifact, ReleaseFile


def pinned_model(workspace: Path) -> tuple[ReleaseArtifact, str]:
    return pinned_causal_model(workspace, "models/Qwen3-8B", "qwen3-original")


def pinned_causal_model(
    workspace: Path, key: str, artifact_id: str
) -> tuple[ReleaseArtifact, str]:
    asset = json.loads((workspace / "configs/runtime-assets-current.json").read_text())[
        "assets"
    ][key]
    inventory_path = Path(asset["inventory"]["path"])
    digest = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    if digest != asset["inventory"]["sha256"]:
        raise ValueError("Model inventory pointer changed")
    inventory = json.loads(inventory_path.read_text())
    files = tuple(
        ReleaseFile(
            path=f["relative"],
            sha256=f["sha256"],
            size_bytes=f["bytes"],
            executable=bool(f["state"][-1] & 0o111),
        )
        for f in inventory["files"]
    )
    return (
        ReleaseArtifact(artifact_id=artifact_id, root=asset["path"], files=files),
        digest,
    )
