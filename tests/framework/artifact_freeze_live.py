"""Compute-only engineering freeze of actual source, without current activation."""

import hashlib
import json
import os
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.releases.artifact_freeze import FileArtifactFreezer
from lab_generate_skill.adapters.releases.artifact_copy import sync_directory
from lab_generate_skill.adapters.releases.files import _inventory
from lab_generate_skill.domain.lifecycle import CancellationRef, OperationContext
from lab_generate_skill.domain.release import ReleaseArtifact, ReleaseFile
from lab_generate_skill.runtime.lifecycle import OperationGuards


class NoCancellation:
    def is_cancelled(self, reference: CancellationRef) -> bool:
        return False


def main() -> int:
    job = os.environ["SLURM_JOB_ID"]
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    project = Path(__file__).resolve().parents[2]
    workspace = project.parents[1]
    source = project / "src" / "lab_generate_skill"
    publication = workspace / "releases" / "artifacts"
    operation = OperationContext(
        operation_id="freeze-" + job,
        run_id="artifact-" + job,
        owner_id="development-publisher",
        deadline=datetime.now(timezone.utc) + timedelta(seconds=600),
    )
    control = OperationGuards(SystemClock(), NoCancellation()).bind(operation)
    result: dict[str, object] = {
        "job_id": job,
        "passed": False,
        "production_release": False,
        "current_switched": False,
    }
    try:
        entries = _inventory(source, control, require_readonly=False)
        if len(entries) > 10000 or any(
            name.endswith((".pyc", ".pyo")) for name in entries
        ):
            raise ValueError(
                "Source inventory exceeds engineering scope or has bytecode"
            )
        files = []
        total = 0
        for name in sorted(entries):
            control.checkpoint()
            path = source / name
            if path.stat().st_size > 32 * 1024 * 1024:
                raise ValueError("Source file too large")
            raw = path.read_bytes()
            total += len(raw)
            if total > 256 * 1024 * 1024:
                raise ValueError("Source tree too large")
            files.append(
                ReleaseFile(
                    path=name,
                    sha256=hashlib.sha256(raw).hexdigest(),
                    size_bytes=len(raw),
                    executable=bool(path.stat().st_mode & 0o111),
                )
            )
        original = ReleaseArtifact(
            artifact_id="development-source", root=str(source), files=tuple(files)
        )
        intent = {
            "schema_version": "engineering-artifact-freeze-intent/1",
            "operation": operation.model_dump(mode="json"),
            "source": original.model_dump(mode="json"),
            "destination": str(publication / ("framework-source-" + job)),
            "production_release": False,
        }
        with (output / "artifact-intent.json").open("x") as stream:
            json.dump(intent, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        sync_directory(output)
        artifact = FileArtifactFreezer(workspace, publication).freeze(
            original, "framework-source-" + job, control
        )
        assert (
            FileArtifactFreezer(workspace, publication).freeze(
                original, artifact.artifact_id, control
            )
            == artifact
        )
        result.update(
            passed=True,
            source=original.model_dump(mode="json"),
            artifact=artifact.model_dump(mode="json"),
            files=len(files),
            bytes=total,
        )
    except BaseException:
        result["traceback"] = traceback.format_exc()
    with (output / "artifact-freeze.json").open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(
        json.dumps(
            {
                k: result[k]
                for k in ("job_id", "passed", "production_release", "current_switched")
            }
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
