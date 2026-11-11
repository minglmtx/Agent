"""Actual isolated installed child entry; no GPU weights loaded in these checks."""

from pathlib import Path
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
import pytest
from lab_generate_skill.adapters.processes.session import FramedProcessSession
from lab_generate_skill.adapters.models.actor_worker_protocol import (
    ActorWorkerCommand,
    MAX_WORKER_PACKET,
    decode_reply,
)
from lab_generate_skill.adapters.models.actor_worker_client import (
    SupervisedActorEngine,
    ActorWorkerFailure,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from actor_engine_fixtures import setup
from test_slurm_commands import guard
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from actor_installation_fixtures import installed_declaration, declaration
from lab_generate_skill.domain.release import ReleaseManifest


def channel(python: Path) -> FramedProcessSession:
    return FramedProcessSession(
        (
            str(python),
            "-I",
            "-B",
            "-m",
            "lab_generate_skill.bootstrap.actor_worker",
        ),
        max_frame_bytes=MAX_WORKER_PACKET,
    )


def test_installed_entry_configuration_and_close(
    installed_sources: InstalledFixture, tmp_path: Path
) -> None:
    engine, _, _, _, _ = setup(tmp_path)
    worker = channel(installed_sources.executable)
    worker.start(guard())
    try:
        init = ActorWorkerCommand(
            session_id="real",
            sequence=1,
            operation="configure",
            controller=current_process_identity(),
            remaining_seconds=10,
            artifact=engine.artifact,
            config=engine.config,
            installation=installed_declaration(installed_sources),
        )
        reply = decode_reply(
            init, worker.exchange(init.model_dump_json().encode(), guard(30))
        )
        assert reply.status == "ok"
        assert reply.owner_guard is not None
        assert reply.owner_guard.controller == current_process_identity()
        assert reply.owner_guard.supervisor.process_id == worker.process_id
        assert reply.owner_guard.worker == reply.worker
        assert reply.worker is not None and reply.worker.process_id != worker.process_id
        assert reply.installed_sources is not None
        assert init.installation is not None
        assert reply.installed_sources.executable == str(installed_sources.executable)
        assert (
            reply.installed_sources.manifest_sha256
            == init.installation.manifest_ref.sha256
        )
        assert any(
            m.name == "lab_generate_skill.bootstrap.actor_worker"
            for m in reply.installed_sources.modules
        )
        close = ActorWorkerCommand(
            session_id="real", sequence=2, operation="close", remaining_seconds=10
        )
        assert (
            decode_reply(
                close, worker.exchange(close.model_dump_json().encode(), guard())
            ).status
            == "ok"
        )
        ended = worker.finish(guard())
        assert (
            ended.returncode == 0
            and not ended.kill_requested
            and worker.capture.complete
        )
        assert not worker.capture.stderr
    finally:
        worker.abort(guard())


@pytest.mark.parametrize("fault", ["python", "unloaded_source", "workspace"])
def test_actual_configure_refuses_foreign_installation(
    installed_sources: InstalledFixture, tmp_path: Path, fault: str
) -> None:
    engine, _, _, _, _ = setup(tmp_path)
    installation = installed_declaration(installed_sources)
    if fault == "python":
        installation = installation.model_copy(
            update={"python_executable": "/other/python"}
        )
    elif fault == "workspace":
        installation = installation.model_copy(update={"workspace_root": str(tmp_path)})
    else:
        data = installed_sources.manifest.model_dump()
        entries = data["artifacts"][0]["files"]
        matches = [
            entry
            for entry in entries
            if entry["path"] == "lab_generate_skill/domain/optional_policies.py"
        ]
        assert len(matches) == 1
        matches[0]["sha256"] = "f" * 64
        installation = declaration(
            ReleaseManifest.model_validate(data),
            installed_sources.workspace,
            installed_sources.executable,
        )
    worker = channel(installed_sources.executable)
    worker.start(guard())
    client = SupervisedActorEngine(
        worker, "real", engine.artifact, engine.config, installation
    )
    try:
        with pytest.raises(ActorWorkerFailure) as caught:
            client.configure(guard(30))
        assert caught.value.reply.status == "error"
        assert caught.value.reply.error is not None
        assert caught.value.reply.error.type_name == "EvidenceIntegrityError"
        assert client.installed_sources is None
        assert worker.capture.termination is not None
        assert worker.capture.termination.state == "reaped"
        with pytest.raises(OwnershipConflict):
            client.configure(guard())
    finally:
        worker.abort(guard())


def test_actual_child_error_reaches_client_without_retry(
    installed_sources: InstalledFixture, tmp_path: Path
) -> None:
    engine, _, request, params, _ = setup(tmp_path)
    Path(engine.artifact.root).chmod(0o755)
    worker = channel(installed_sources.executable)
    worker.start(guard())
    client = SupervisedActorEngine(
        worker,
        "real",
        engine.artifact,
        engine.config,
        installed_declaration(installed_sources),
    )
    try:
        with pytest.raises(ActorWorkerFailure) as caught:
            client.validate(request, params, guard(30))
        assert caught.value.reply.error is not None
        assert caught.value.reply.error.type_name == "EvidenceIntegrityError"
        assert (
            worker.capture.termination is not None
            and worker.capture.termination.state == "reaped"
        )
        with pytest.raises(OwnershipConflict):
            client.generate(request, params, guard())
    finally:
        worker.abort(guard())


def test_actual_child_duplicate_command_fails_closed(
    installed_sources: InstalledFixture, tmp_path: Path
) -> None:
    engine, _, _, _, _ = setup(tmp_path)
    worker = channel(installed_sources.executable)
    worker.start(guard())
    init = ActorWorkerCommand(
        session_id="real",
        sequence=1,
        operation="configure",
        controller=current_process_identity(),
        remaining_seconds=10,
        artifact=engine.artifact,
        config=engine.config,
        installation=installed_declaration(installed_sources),
    )
    try:
        assert (
            decode_reply(
                init, worker.exchange(init.model_dump_json().encode(), guard(30))
            ).status
            == "ok"
        )
        reply = decode_reply(
            init, worker.exchange(init.model_dump_json().encode(), guard())
        )
        assert reply.status == "error" and reply.error is not None
        assert reply.error.type_name == "OwnershipConflict"
        assert worker.finish(guard()).returncode == 0
    finally:
        worker.abort(guard())
