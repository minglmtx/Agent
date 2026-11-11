"""Installation admission: exact bytes, malformed data, no factory on failure.

Actual interpreter/package checks run in test_generator_worker_process and
test_installed_sources. These unit receipts explicitly confer no runtime rights.
"""

from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.release_installation import InstalledReleaseModule
from lab_generate_skill.domain.generator_installation import (
    GeneratorInstallation,
    GeneratorInstalledSources,
)
from lab_generate_skill.domain.errors import GeneratorInputBudgetExceeded
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.models.generator_worker_protocol import (
    GeneratorWorkerCommand,
    decode_reply,
)
from lab_generate_skill.adapters.models.generator_worker_client import (
    GeneratorWorkerFailure,
)
from generator_installation_fixtures import unit_declaration, unit_verifier
from generator_worker_fixtures import worker_case
from test_generator_worker import commands
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "field,value",
    [
        ("workspace_root", ""),
        ("workspace_root", "relative"),
        ("workspace_root", "/unit/../other"),
        ("workspace_root", "/unit//other"),
        ("workspace_root", "/unit/"),
        ("workspace_root", "/unit\0"),
        ("workspace_root", 1),
        ("python_executable", None),
        ("python_executable", []),
        ("python_executable", "/" + "a" * 4096),
        ("schema_version", "generator-installation/0"),
    ],
)
def test_invalid_installation_paths_and_types(field: str, value: Any) -> None:
    data = unit_declaration().model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        GeneratorInstallation.model_validate(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("size_bytes", 1),
        ("sha256", "f" * 64),
        ("visibility", "public"),
        ("content_schema", "other/1"),
    ],
)
def test_manifest_reference_must_pin_exact_private_bytes(
    field: str, value: Any
) -> None:
    data = unit_declaration().model_dump()
    data["manifest_ref"][field] = value
    with pytest.raises(ValidationError):
        GeneratorInstallation.model_validate(data)


@pytest.mark.parametrize(
    "fault", ["empty", "duplicate", "outside", "unordered", "wrong_type", "version"]
)
def test_observed_modules_reject_incomplete_or_ambiguous_receipt(fault: str) -> None:
    receipt = unit_verifier(unit_declaration(), guard())
    data = receipt.model_dump()
    original = data["modules"][0]
    if fault == "empty":
        data["modules"] = ()
    elif fault == "duplicate":
        data["modules"] = (original, original)
    elif fault == "outside":
        data["package_root"] = "/other"
    elif fault == "unordered":
        data["modules"] = (
            {
                "name": "lab_generate_skill.zz",
                "filename": "/unit/site/lab_generate_skill/zz.py",
            },
            original,
        )
    elif fault == "wrong_type":
        data["modules"] = "lab_generate_skill"
    else:
        data["schema_version"] = "generator-installed-sources/0"
    with pytest.raises(ValidationError):
        GeneratorInstalledSources.model_validate(data)


@pytest.mark.parametrize(
    "name,filename",
    [
        ("other", "/unit/other.py"),
        ("lab_generate_skill.foo", "/unit/lab_generate_skill/bar.py"),
        ("lab_generate_skill", "/unit/lab_generate_skill/__init__.pyc"),
        ("lab_generate_skill", "/unit/../lab_generate_skill/__init__.py"),
    ],
)
def test_module_name_and_source_file_must_agree(name: str, filename: str) -> None:
    with pytest.raises(ValidationError):
        InstalledReleaseModule(name=name, filename=filename)


@pytest.mark.parametrize("fault", ["missing", "old_command", "wrong_operation"])
def test_configure_requires_installation_without_legacy_fallback(
    tmp_path: Path, fault: str
) -> None:
    configure, _, close, loader, _ = commands(tmp_path)
    data = configure.model_dump()
    if fault == "missing":
        data["installation"] = None
    elif fault == "old_command":
        data["schema_version"] = "generator-worker-command/1"
    else:
        data = {**close.model_dump(), "installation": data["installation"]}
    with pytest.raises(ValidationError):
        GeneratorWorkerCommand.model_validate(data)
    assert loader.loads == 0


@pytest.mark.parametrize(
    "fault", ["missing", "old_reply", "release", "digest", "executable"]
)
def test_successful_handshake_must_return_original_installation(
    tmp_path: Path, fault: str
) -> None:
    configure, _, _, _, service = commands(tmp_path)
    reply = service.handle(configure)
    sources = reply.installed_sources
    assert sources is not None
    if fault == "missing":
        reply = reply.model_copy(update={"installed_sources": None})
    elif fault == "old_reply":
        reply = reply.model_copy(update={"schema_version": "generator-worker-reply/2"})
    else:
        change = {
            "release": {"release_id": "other"},
            "digest": {"manifest_sha256": "e" * 64},
            "executable": {"executable": "/other/python"},
        }[fault]
        reply = reply.model_copy(
            update={"installed_sources": sources.model_copy(update=change)}
        )
    with pytest.raises(ValueError):
        decode_reply(configure, reply.model_dump_json().encode())
    service.close()


@pytest.mark.parametrize("fault", ["io", "budget_type", "foreign", "malformed"])
def test_verification_failure_never_constructs_engine_and_cannot_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    _, loader, _, _, control, service, channel, client = worker_case(tmp_path)
    factory_calls: list[bool] = []

    def forbidden_factory(*args: Any) -> Any:
        factory_calls.append(True)
        pytest.fail("engine constructed before installation verified")

    def bad(
        installation: GeneratorInstallation, guard: OperationControl
    ) -> GeneratorInstalledSources:
        if fault == "io":
            raise OSError("installation read failed")
        if fault == "budget_type":
            raise GeneratorInputBudgetExceeded("not an inference rejection")
        receipt = unit_verifier(installation, guard)
        return receipt.model_copy(
            update={"release_id": "foreign"} if fault == "foreign" else {"modules": ()}
        )

    monkeypatch.setattr(service, "_factory", forbidden_factory)
    monkeypatch.setattr(service, "_installation_verifier", bad)
    with pytest.raises(GeneratorWorkerFailure) as caught:
        client.configure(control)
    assert caught.value.reply.status == "error"
    assert caught.value.reply.installed_sources is None
    assert service.closed and channel.aborts == 1
    assert not factory_calls and loader.loads == 0 and client.installed_sources is None
    from lab_generate_skill.domain.errors import OwnershipConflict

    with pytest.raises(OwnershipConflict):
        client.configure(control)
    assert len(channel.sent) == 1


def test_receipt_is_retained_through_close_without_reverification(
    tmp_path: Path,
) -> None:
    _, _, _, _, control, _, channel, client = worker_case(tmp_path)
    assert client.installed_sources is None
    first = client.configure(control)
    receipt = client.installed_sources
    assert receipt is not None
    assert client.configure(control) == first and len(channel.sent) == 1
    client.close(control)
    assert client.installed_sources == receipt
