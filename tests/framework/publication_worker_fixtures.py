"""Explicit synthetic wire/transport facts; never actual installed provenance."""

import hashlib
import os
from pathlib import Path
from lab_generate_skill.domain.release import ReleaseManifest, ReleaseFile
from lab_generate_skill.domain.release_installation import (
    ReleaseInstallation,
    InstalledReleaseSources,
    InstalledReleaseModule,
)
from lab_generate_skill.domain.evidence_storage import EvidenceStorageConfig
from lab_generate_skill.domain.storage_scope import StorageScope
from lab_generate_skill.domain.storage_launch import StorageLaunch
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.slurm_allocation import SlurmCgroupMembership
from lab_generate_skill.domain.release_current import ReleaseCurrentSnapshot
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    ProcessTermination,
)
from lab_generate_skill.adapters.storage.publication_protocol import (
    PublicationReadCommand,
    PublicationReadReply,
    encode_publication_command,
    encode_publication_reply,
    ENTRY,
)
from storage_scope_fixtures import scope, operation
from storage_launch_fixtures import selection


def inputs(
    root: Path,
    *,
    entry: str = ENTRY,
) -> tuple[StorageLaunch, ReleaseCurrentSnapshot, PublicationReadCommand]:
    bound = scope()
    installation = bound.config.installation
    data = installation.manifest.model_dump()
    extra = ReleaseFile(
        path=entry.replace(".", "/") + ".py",
        sha256="0" * 64,
        size_bytes=0,
        executable=False,
    )
    data["artifacts"][0]["files"] = tuple(
        sorted(
            (*data["artifacts"][0]["files"], extra.model_dump()),
            key=lambda v: v["path"],
        )
    )
    manifest = ReleaseManifest.model_validate(data)
    raw = manifest.model_dump_json().encode()
    digest = hashlib.sha256(raw).hexdigest()
    ref = installation.manifest_ref.model_copy(
        update={
            "sha256": digest,
            "size_bytes": len(raw),
            "uri": "cas://sha256/" + digest,
        }
    )
    installation = ReleaseInstallation.model_validate(
        installation.model_copy(
            update={
                "manifest": manifest,
                "manifest_ref": ref,
                "workspace_root": str(root),
            }
        )
    )
    config = EvidenceStorageConfig.model_validate(
        bound.config.model_copy(
            update={
                "installation": installation,
                "evidence_root": str(root / "data"),
                "session_root": str(root / "sessions"),
            }
        )
    )
    bound = StorageScope.model_validate(
        bound.model_copy(
            update={
                "config": config,
                "workspace_root": str(root),
                "writer": current_process_identity(),
                "execution": bound.execution.model_copy(update={"uid": os.getuid()}),
                "run": bound.run.model_copy(update={"release_ref": ref}),
                "binding": bound.binding.model_copy(
                    update={"storage_config_sha256": config.sha256}
                ),
            }
        )
    )
    launch, snapshot = selection(bound)
    command = PublicationReadCommand(
        scope=launch.scope,
        deployment=launch.deployment,
        root=str(root / "current"),
        operation=operation(launch.scope),
    )
    return launch, snapshot, command


def reply(
    command: PublicationReadCommand,
    snapshot: ReleaseCurrentSnapshot,
    *,
    entry: str = ENTRY,
) -> PublicationReadReply:
    worker = ProcessIdentity(
        node_id=command.scope.writer.node_id,
        boot_id=command.scope.writer.boot_id,
        process_id=command.scope.writer.process_id + 10000,
        start_ticks=1,
    )
    declaration = command.scope.config.installation
    root = declaration.manifest.artifacts[0].root
    sources = InstalledReleaseSources(
        release_id=declaration.manifest.release_id,
        manifest_sha256=declaration.manifest_ref.sha256,
        executable=declaration.python_executable,
        package_root=root + "/lab_generate_skill",
        distribution_version="0.1.0",
        modules=(
            InstalledReleaseModule(
                name="lab_generate_skill",
                filename=root + "/lab_generate_skill/__init__.py",
            ),
            InstalledReleaseModule(
                name=entry, filename=root + "/" + entry.replace(".", "/") + ".py"
            ),
        ),
    )
    membership = SlurmCgroupMembership(
        job_id=command.scope.execution.raw_job_id,
        step_id="batch",
        writer=worker,
        uid=command.scope.execution.uid,
        user_path="/sys/fs/cgroup/system.slice/slurmstepd.scope/job_"
        + command.scope.execution.raw_job_id
        + "/step_batch/user",
        mount_id=1,
        device=1,
        user_inode=2,
        task_inode=3,
    )
    return PublicationReadReply(
        command_sha256=hashlib.sha256(encode_publication_command(command)).hexdigest(),
        worker=worker,
        phase="completion",
        error=None,
        installed_sources=sources,
        membership=membership,
        snapshot=snapshot,
    )


def capture(
    command: PublicationReadCommand, snapshot: ReleaseCurrentSnapshot
) -> CommandCapture:
    result = reply(command, snapshot)
    return CommandCapture(
        (command.scope.config.installation.python_executable, "-I", "-B", "-m", ENTRY),
        0,
        encode_publication_reply(result),
        b"",
        True,
        ProcessTermination(result.worker.process_id, "reaped", 0, False),
    )
