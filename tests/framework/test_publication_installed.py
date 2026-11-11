"""Actual child read errors cannot initialize, repair or return candidate facts."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.storage.publication_reader import (
    StoragePublicationReader,
)
from lab_generate_skill.adapters.storage.publication_transport import (
    PublicationReadFailure,
)
from lab_generate_skill.adapters.storage.publication_protocol import (
    encode_publication_command,
    decode_publication_reply,
    ENTRY,
)
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_run_journal import CancelSwitch
from test_slurm_commands import guard
from installed_publication_fixtures import setup
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)


@pytest.mark.parametrize("case", ["missing", "corrupt", "symlink"])
def test_installed_errors_leave_original_files(
    tmp_path: Path, installed_sources: InstalledFixture, case: str
) -> None:
    launch, _, command = setup(tmp_path, installed_sources, publish=case != "missing")
    root = Path(command.root)
    if case == "corrupt":
        (root / "system-current.json").write_bytes(b"{broken")
    if case == "symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(root, target_is_directory=True)
        root = alias
    before = {
        p.name: p.read_bytes() for p in Path(command.root).iterdir() if p.is_file()
    }
    reader = StoragePublicationReader(
        root, launch, OperationGuards(SystemClock(), CancelSwitch())
    )
    with pytest.raises(PublicationReadFailure) as caught:
        reader.read(command.operation, control=guard(60))
    failure = caught.value
    assert failure.phase == "worker" and failure.reply is not None
    assert failure.reply.phase == "read" and failure.reply.error is not None
    assert failure.reply.installed_sources is not None
    assert failure.capture is not None and failure.capture.termination is not None
    assert failure.capture.termination.state == "reaped"
    assert reader.last_execution is None
    assert {
        p.name: p.read_bytes() for p in Path(command.root).iterdir() if p.is_file()
    } == before


def test_wrong_parent_rejected_before_installation(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    _, _, command = setup(tmp_path, installed_sources)
    command = command.model_copy(
        update={
            "scope": command.scope.model_copy(
                update={
                    "writer": command.scope.writer.model_copy(
                        update={"start_ticks": command.scope.writer.start_ticks + 1}
                    )
                }
            )
        }
    )
    raw = encode_publication_command(command)
    observed = ProcessRunner(max_output_bytes=13 * 1024 * 1024).run(
        (str(installed_sources.executable), "-I", "-B", "-m", ENTRY),
        guard(30),
        stdin_bytes=raw,
    )
    reply = decode_publication_reply(raw, observed.stdout)
    assert reply.error is not None and reply.phase == "parent_guard"
    assert reply.installed_sources is None and reply.snapshot is None


CLOSE_FAULT = """
import os
from lab_generate_skill.bootstrap.storage_publication import main
original=os.close
def close(fd):
    target=os.readlink('/proc/self/fd/'+str(fd))
    original(fd)
    if target=='anon_inode:[pidfd]':
        raise OSError(5,'injected close acknowledgement loss')
os.close=close
raise SystemExit(main())
"""


@pytest.mark.parametrize("read_error", [False, True])
def test_read_and_owner_close_errors_preserved(
    tmp_path: Path, installed_sources: InstalledFixture, read_error: bool
) -> None:
    _, snapshot, command = setup(tmp_path, installed_sources)
    if read_error:
        (Path(command.root) / "system-current.json").write_bytes(b"{bad")
    raw = encode_publication_command(command)
    observed = ProcessRunner(max_output_bytes=13 * 1024 * 1024).run(
        (str(installed_sources.executable), "-I", "-B", "-c", CLOSE_FAULT),
        guard(30),
        stdin_bytes=raw,
    )
    reply = decode_publication_reply(raw, observed.stdout)
    assert reply.error is not None
    assert reply.error.type_name == "ExceptionGroup"
    assert "OSError" in {child.type_name for child in reply.error.children}
    if read_error:
        assert "EvidenceIntegrityError" in {
            child.type_name for child in reply.error.children
        }
        assert reply.snapshot is None
    else:
        assert reply.snapshot == snapshot  # candidate only; error prevents confirmation


def test_fixed_entry_never_reads_current_in_parent(
    tmp_path: Path, installed_sources: InstalledFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lab_generate_skill.adapters.releases.current import FileReleaseCurrent

    launch, snapshot, command = setup(tmp_path, installed_sources)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("current I/O escaped into original controller")

    monkeypatch.setattr(FileReleaseCurrent, "read", forbidden)
    reader = StoragePublicationReader(
        Path(command.root), launch, OperationGuards(SystemClock(), CancelSwitch())
    )
    assert reader.read(command.operation, control=guard(60)) == snapshot
    execution = reader.last_execution
    assert execution is not None and execution.capture.argv[-2:] == ("-m", ENTRY)
    assert execution.reply.worker.process_id != command.scope.writer.process_id
    assert execution.reply.installed_sources is not None


@pytest.mark.parametrize("case", ["wrong_python", "wrong_code_pin"])
def test_installation_failure_before_current(
    tmp_path: Path, installed_sources: InstalledFixture, case: str
) -> None:
    import hashlib
    from lab_generate_skill.domain.release import ReleaseManifest
    from lab_generate_skill.domain.release_installation import ReleaseInstallation
    from lab_generate_skill.domain.evidence_storage import EvidenceStorageConfig
    from lab_generate_skill.domain.storage_scope import StorageScope

    _, _, command = setup(tmp_path, installed_sources)
    original = command.scope.config.installation
    if case == "wrong_python":
        installation = ReleaseInstallation.model_validate(
            original.model_copy(update={"python_executable": "/wrong/python"})
        )
    else:
        data = original.manifest.model_dump()
        data["artifacts"][0]["files"][0]["sha256"] = "0" * 64
        manifest = ReleaseManifest.model_validate(data)
        content = manifest.model_dump_json().encode()
        digest = hashlib.sha256(content).hexdigest()
        ref = original.manifest_ref.model_copy(
            update={
                "sha256": digest,
                "uri": "cas://sha256/" + digest,
                "size_bytes": len(content),
            }
        )
        installation = ReleaseInstallation.model_validate(
            original.model_copy(update={"manifest": manifest, "manifest_ref": ref})
        )
    config = EvidenceStorageConfig.model_validate(
        command.scope.config.model_copy(update={"installation": installation})
    )
    scope = StorageScope.model_validate(
        command.scope.model_copy(
            update={
                "config": config,
                "binding": command.scope.binding.model_copy(
                    update={"storage_config_sha256": config.sha256}
                ),
                "run": command.scope.run.model_copy(
                    update={"release_ref": installation.manifest_ref}
                ),
            }
        )
    )
    command = command.model_copy(update={"scope": scope})
    # Corrupt current too: installation must reject BEFORE even trying to parse it.
    path = Path(command.root) / "system-current.json"
    path.write_bytes(b"{bad current")
    raw = encode_publication_command(command)
    captured = ProcessRunner(max_output_bytes=13 * 1024 * 1024).run(
        (str(installed_sources.executable), "-I", "-B", "-m", ENTRY),
        guard(30),
        stdin_bytes=raw,
    )
    result = decode_publication_reply(raw, captured.stdout)
    assert result.phase == "installation" and result.error is not None
    assert result.snapshot is None and result.membership is None
    assert path.read_bytes() == b"{bad current"
