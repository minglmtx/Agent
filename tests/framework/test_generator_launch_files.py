"""Launch code/Python files and raw envelopes, separate from live permissions."""

import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.models.generator_launch_files import (
    verify_launch_files,
    verify_system_command,
)
from lab_generate_skill.adapters.models.generator_authority_evidence import (
    require_step_raw,
)
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from cgroup_fixtures import Control
from slurm_step_fixtures import target
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)


def test_real_frozen_launch_files(installed_sources: InstalledFixture) -> None:
    f = installed_sources
    verify_launch_files(f.manifest, f.workspace, str(f.executable), Control())
    verify_launch_files(f.manifest, f.workspace, str(f.executable), Control())
    verify_system_command("/usr/bin/srun", Control())


@pytest.mark.parametrize("which", ["python", "workspace", "hash", "mode"])
def test_launch_file_mismatch(
    installed_sources: InstalledFixture, which: str, tmp_path: Path
) -> None:
    f = installed_sources
    manifest = f.manifest
    root = f.workspace
    executable = str(f.executable)
    if which == "python":
        executable = str(f.executable.parent / "unbound-python")
    elif which == "workspace":
        root = tmp_path
    else:
        a = next(a for a in manifest.artifacts if a.artifact_id == "python-files")
        file = a.files[0].model_copy(
            update={"sha256": "0" * 64} if which == "hash" else {"executable": False}
        )
        manifest = manifest.model_copy(
            update={
                "artifacts": tuple(
                    (
                        x.model_copy(update={"files": (file,)})
                        if x.artifact_id == a.artifact_id
                        else x
                    )
                    for x in manifest.artifacts
                )
            }
        )
    with pytest.raises(EvidenceIntegrityError):
        verify_launch_files(manifest, root, executable, Control())


@pytest.mark.parametrize("which", ["user", "relative", "alias"])
def test_scheduler_command_trust(which: str, tmp_path: Path) -> None:
    p = tmp_path / "srun"
    p.write_bytes(b"exit")
    p.chmod(0o555)
    path = (
        str(p)
        if which == "user"
        else ("srun" if which == "relative" else "/usr/bin/../bin/srun")
    )
    with pytest.raises(EvidenceIntegrityError):
        verify_system_command(path, Control())


@pytest.mark.parametrize(
    "which",
    [
        "valid",
        "empty",
        "list",
        "duplicate",
        "phase",
        "target",
        "error",
        "missing_error",
        "kernel",
        "commands",
    ],
)
def test_step_raw_envelope(tmp_path: Path, which: str) -> None:
    store = FileEvidenceStore(tmp_path)
    t = target()
    value: dict[str, Any] = {
        "schema_version": "generator-step-raw/1",
        "phase": "started",
        "target": t.model_dump(mode="json"),
        "error": None,
        "kernel": [{}],
        "commands": [{}],
    }
    if which == "phase":
        value["phase"] = "closed"
    if which == "target":
        value["target"] = None
    if which == "error":
        value["error"] = {"type": "failed"}
    if which == "missing_error":
        del value["error"]
    if which in ("kernel", "commands"):
        value[which] = []
    raw = json.dumps(value).encode()
    if which == "empty":
        raw = b""
    if which == "list":
        raw = b"[]"
    if which == "duplicate":
        raw = b'{"phase":"started","phase":"started"}'
    ref = store.put(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="generator-step-raw/1",
            visibility="private",
            producer="test",
        ),
    )
    if which == "valid":
        require_step_raw(store, ref, t, "started", Control())
    else:
        with pytest.raises(EvidenceIntegrityError):
            require_step_raw(store, ref, t, "started", Control())
