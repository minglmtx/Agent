"""Unified wire and guard-before-factory admission; no legacy fallback."""

from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.models.generator_worker_protocol import (
    GeneratorWorkerCommand,
    decode_reply,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from test_generator_worker import commands


@pytest.mark.parametrize(
    "change",
    [
        {"controller": None},
        {"controller": {}},
        {"controller": []},
        {"schema_version": "generator-worker-command/2"},
    ],
)
def test_configure_requires_original_controller(
    tmp_path: Path, change: dict[str, Any]
) -> None:
    configure, _, _, loader, _ = commands(tmp_path)
    with pytest.raises(ValidationError):
        GeneratorWorkerCommand.model_validate(configure.model_copy(update=change))
    assert loader.loads == 0


@pytest.mark.parametrize(
    "change",
    [
        {"owner_guard": None},
        {"owner_guard": {}},
        {"schema_version": "generator-worker-reply/3"},
    ],
)
def test_handshake_requires_current_guard(
    tmp_path: Path, change: dict[str, Any]
) -> None:
    configure, _, _, _, service = commands(tmp_path)
    reply = service.handle(configure)
    with pytest.raises(ValidationError):
        decode_reply(
            configure,
            reply.model_copy(update=change).model_dump_json(warnings=False).encode(),
        )
    service.close()


@pytest.mark.parametrize("which", ["failure", "foreign", "invalid"])
def test_guard_rejection_before_installation_and_factory(
    tmp_path: Path, which: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure, _, _, loader, service = commands(tmp_path)
    original = service._guard_verifier

    def verify(*args: Any) -> Any:
        if which == "failure":
            raise OwnershipConflict("guard unavailable")
        if which == "invalid":
            return {}
        value = original(*args)
        return value.model_copy(
            update={
                "controller": value.controller.model_copy(
                    update={"start_ticks": value.controller.start_ticks + 1}
                )
            }
        )

    def forbidden(*args: Any) -> Any:
        pytest.fail("installation/factory before guard")

    monkeypatch.setattr(service, "_guard_verifier", verify)
    monkeypatch.setattr(service, "_installation_verifier", forbidden)
    monkeypatch.setattr(service, "_factory", forbidden)
    reply = service.handle(configure)
    assert reply.status == "error" and service.closed
    assert reply.worker is None and reply.owner_guard is None and loader.loads == 0
