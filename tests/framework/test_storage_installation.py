"""Mandatory release binding, bounded frames and pre-storage actual verification."""

import hashlib
import struct
from datetime import datetime, timezone
from pathlib import Path
import pytest
from lab_generate_skill.domain.evidence_storage import EvidenceStorageConfig
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.release import ReleaseManifest
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.adapters.storage.registered_protocol import (
    RegisteredStorageCommand,
    MAX_REGISTERED_HEADER_BYTES,
    encode_registered_command,
    decode_registered_command,
    decode_registered_reply,
    _head,
    _split,
)
from lab_generate_skill.adapters.storage.resolver_protocol import (
    StorageResolutionCommand,
)
from lab_generate_skill.adapters.storage.registered_transport import (
    RegisteredStorageTransport,
    RegisteredStorageFailure,
)
from lab_generate_skill.adapters.storage.resolver_transport import (
    StorageResolverTransport,
    StorageResolverFailure,
)
from lab_generate_skill.adapters.storage.installation_receipt import (
    check_storage_installation,
)
from registered_storage_fixtures import request, roots, ExplicitAdmission
from storage_installation_fixtures import unit_storage_sources
from generator_release_fixtures import metadata
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "fault", ["missing", "old_config", "old_command", "release", "binding"]
)
def test_incompatible_configuration_before_effects(tmp_path: Path, fault: str) -> None:
    cmd = request(tmp_path)
    data = cmd.model_dump()
    if fault == "missing":
        del data["config"]["installation"]
    elif fault == "old_config":
        data["config"]["schema_version"] = "evidence-storage-config/1"
    elif fault == "old_command":
        data["schema_version"] = "registered-storage-command/1"
    elif fault == "release":
        data["binding"]["release_id"] = "other"
    else:
        data["config"]["installation"]["python_executable"] = "/other/python"
    with pytest.raises(ValueError):
        RegisteredStorageCommand.model_validate(data)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "fault", ["missing", "release", "digest", "python", "entry", "foreign_module"]
)
def test_reply_requires_bound_release_and_actual_entry(
    tmp_path: Path, fault: str
) -> None:
    cmd = request(tmp_path)
    sources = unit_storage_sources(cmd.config.installation)
    if fault == "missing":
        value = None
    elif fault == "entry":
        value = sources.model_copy(update={"modules": sources.modules[:1]})
    elif fault == "foreign_module":
        value = sources.model_copy(
            update={
                "modules": (
                    sources.modules[0].model_copy(
                        update={"filename": "/other/lab_generate_skill/__init__.py"}
                    ),
                )
            }
        )
    else:
        field = {
            "release": "release_id",
            "digest": "manifest_sha256",
            "python": "executable",
        }[fault]
        value = sources.model_copy(
            update={
                field: (
                    "f" * 64
                    if fault == "digest"
                    else "/other/python" if fault == "python" else "other"
                )
            }
        )
    with pytest.raises(ValueError):
        check_storage_installation(
            cmd.config,
            value,
            entry_module="lab_generate_skill.bootstrap.evidence_worker",
            required=True,
        )


def test_header_exact_limit_and_overflow() -> None:
    class Header(Contract):
        content: str

    overhead = len(Header(content="").model_dump_json().encode())
    valid = Header(content="x" * (MAX_REGISTERED_HEADER_BYTES - overhead))
    packet = _head(valid)
    assert len(packet) == MAX_REGISTERED_HEADER_BYTES + 4
    assert _split(packet)[1] == b""
    with pytest.raises(ValueError):
        _head(Header(content=valid.content + "x"))
    with pytest.raises(ValueError):
        _split(struct.pack(">I", MAX_REGISTERED_HEADER_BYTES + 1) + packet[4:])


def wrong_source(cmd: RegisteredStorageCommand) -> RegisteredStorageCommand:
    installation = cmd.config.installation
    data = installation.manifest.model_dump()
    changed = False
    for artifact in data["artifacts"]:
        for file in artifact["files"]:
            if file["path"] == "lab_generate_skill/__init__.py":
                file["sha256"] = "0" * 64
                changed = True
    assert changed
    manifest = ReleaseManifest.model_validate(data)
    installation = installation.model_copy(
        update={
            "manifest": manifest,
            "manifest_ref": evidence_reference(
                manifest.model_dump_json().encode(), metadata("release-manifest/1")
            ),
        }
    )
    config = cmd.config.model_copy(update={"installation": installation})
    return cmd.model_copy(
        update={
            "config": config,
            "binding": cmd.binding.model_copy(
                update={"storage_config_sha256": config.sha256}
            ),
        }
    )


@pytest.mark.parametrize("resolver", [False, True])
def test_actual_wrong_installation_precedes_all_storage_effects(
    tmp_path: Path, installed_sources: InstalledFixture, resolver: bool
) -> None:
    roots(tmp_path)
    cmd = wrong_source(
        request(tmp_path, create=not resolver, installation=installed_sources)
    )
    if resolver:
        cleanup = cmd.operation.cleanup(
            "cleanup", now=datetime.now(timezone.utc), seconds=60
        )
        command = StorageResolutionCommand(original=cmd, cleanup=cleanup, ending=None)
        with pytest.raises(StorageResolverFailure) as failed_resolver:
            StorageResolverTransport(
                str(installed_sources.executable), ExplicitAdmission(cmd)
            ).execute(command, b"evidence", guard(60))
        result = failed_resolver.value.result
        assert result is not None and result.reply.phase == "installation"
        assert (
            result.reply.installed_sources is None
            and result.reply.resolution is None
            and result.snapshot is None
        )
    else:
        with pytest.raises(RegisteredStorageFailure) as failed_worker:
            RegisteredStorageTransport(
                str(installed_sources.executable), ExplicitAdmission(cmd)
            ).execute(cmd, b"", guard(60))
        original = failed_worker.value.result
        assert original is not None and original.reply.phase == "installation"
        assert (
            original.reply.installed_sources is None
            and original.reply.intent is None
            and original.snapshot is None
        )
    assert not list((tmp_path / "sessions").iterdir())
    assert not list((tmp_path / "data").iterdir())


def test_actual_installation_larger_than_old_header_is_bound_in_reply(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    roots(tmp_path)
    cmd = request(tmp_path, create=True, installation=installed_sources)
    packet = encode_registered_command(cmd)
    assert struct.unpack(">I", packet[:4])[0] > 65536
    assert decode_registered_command(packet) == (cmd, b"")
    result = RegisteredStorageTransport(
        str(installed_sources.executable), ExplicitAdmission(cmd)
    ).execute(cmd, b"", guard(60))
    sources = result.result.reply.installed_sources
    assert (
        sources is not None
        and sources.manifest_sha256 == cmd.config.installation.manifest_ref.sha256
    )
    assert sources.executable == str(installed_sources.executable)
    assert decode_registered_reply(packet, result.capture.stdout) == result.result
