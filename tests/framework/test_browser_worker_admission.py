"""Worker admission and returned-data boundaries, without installing browsers."""

import json
import pytest
from lab_generate_skill.adapters.browsergym.worker_service import BrowserService
from lab_generate_skill.adapters.browsergym.worker_protocol import (
    decode_reply,
    decode_command,
)
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.release_installation import (
    ReleaseInstallation,
    InstalledReleaseSources,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.browser_session import RawBrowserSession
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from browser_worker_fixtures import case, sources
from generator_worker_fixtures import unit_guard
from browsergym_fixtures import operation
from test_browser_worker import first
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "failure", ["guard", "installation", "wrong_installation", "missing_entry"]
)
def test_admission_failure_precedes_factory(failure: str) -> None:
    calls: list[str] = []

    def factory(config: BrowserWorkerConfiguration) -> RawBrowserSession:
        calls.append("factory")
        raise AssertionError("Factory must not run on failed admission")

    def verify_guard(
        expected: ProcessIdentity, control: OperationControl
    ) -> ProcessOwnerGuard:
        calls.append("guard")
        if failure == "guard":
            raise PermissionError("original controller unavailable")
        return unit_guard(expected, control)

    def verify_sources(
        expected: ReleaseInstallation, control: OperationControl
    ) -> InstalledReleaseSources:
        calls.append("installation")
        if failure == "installation":
            raise OSError("installation read failed")
        value = sources(expected, control)
        if failure == "wrong_installation":
            return value.model_copy(update={"manifest_sha256": "f" * 64})
        return value.model_copy(
            update={
                "modules": tuple(
                    m for m in value.modules if not m.name.endswith(".browser_worker")
                )
            }
        )

    service = BrowserService(factory, verify_sources, verify_guard)
    reply = service.handle(first())
    assert reply.error is not None
    assert (
        reply.error.type_name
        == {
            "guard": "PermissionError",
            "installation": "OSError",
            "wrong_installation": "OwnershipConflict",
            "missing_entry": "OwnershipConflict",
        }[failure]
    )
    assert reply.owner_guard is None and reply.installed_sources is None
    assert "factory" not in calls and service.closed
    assert calls == (["guard"] if failure == "guard" else ["guard", "installation"])


@pytest.mark.parametrize(
    "changed",
    [
        "session",
        "sequence",
        "digest",
        "operation",
        "scope",
        "controller",
        "installation",
    ],
)
def test_reply_must_match_original_start_and_scope(changed: str) -> None:
    engine, service, channel, client = case()
    client.start(operation(client.spec, "start"), control=guard(30))
    configuration_fact = changed in ("controller", "installation")
    command = decode_command(channel.calls[0 if configuration_fact else 1])
    reply = client.configuration_reply if configuration_fact else client.last_reply
    assert reply is not None
    values = reply.model_dump(mode="json")
    if changed == "session":
        values["session_id"] = "other"
    elif changed == "sequence":
        values["sequence"] = 3
    elif changed == "digest":
        values["command_sha256"] = "f" * 64
    elif changed == "operation":
        values["readout"]["operation"]["operation_id"] = "other"
    elif changed == "scope":
        values["readout"]["scope"]["context_id"] = "other"
        values["readout"]["observation"]["context_id"] = "other"
    elif changed == "controller":
        values["owner_guard"]["controller"]["start_ticks"] += 1
    else:
        values["installed_sources"]["manifest_sha256"] = "f" * 64
    # Canonical encoding must be derived through the typed envelope so this
    # exercises identity matching rather than whitespace alone.
    from lab_generate_skill.adapters.browsergym.worker_protocol import (
        BrowserWorkerReply,
    )

    raw = (
        BrowserWorkerReply.model_validate_json(json.dumps(values))
        .model_dump_json()
        .encode()
    )
    with pytest.raises(ValueError):
        decode_reply(command, client.spec, raw)
