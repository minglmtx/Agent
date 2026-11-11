"""Complete failed startup bytes survive original RPC and native abort; no retry."""

import base64
import errno
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.map_artifacts import site_storage
from lab_generate_skill.adapters.sites.worker_client import SiteWorkerFailure
from lab_generate_skill.domain.errors import InvalidTransition
from lab_generate_skill.domain.map_startup import (
    MapStartupHttpFailureRecord,
    MapStartupHttpResponse,
)
from lab_generate_skill.sites.map.startup_failure import MapHttpStartupFailure
from lab_generate_skill.sites.map.service_readiness import HTTP_PROBE
from map_registered_worker_fixtures import RegisteredMapCase
from map_services_fixtures import generation_case
from site_instance_fixtures import node_path
from test_site_resource import enter, inspect
from test_slurm_commands import guard


def reply(status: int, body: bytes) -> bytes:
    return json.dumps(
        {"status": status, "body_base64": base64.b64encode(body).decode()}
    ).encode()


@pytest.mark.parametrize(
    "status,body",
    [
        (301, b""),
        (404, b"not found"),
        (503, b"\xffnative failure\x00"),
        (500, b"x" * (4 * 1024**2)),
    ],
)
def test_original_non200_remains_failed_and_full_response_is_typed(
    node_path: Path, status: int, body: bytes
) -> None:
    with generation_case(node_path) as (generation, commands, group):
        commands.http = [reply(200, b"ready")] * 4 + [reply(status, body)]
        with pytest.raises(MapHttpStartupFailure) as caught:
            generation.start(guard(600))
        error = caught.value
        assert base64.b64decode(error.response.body_base64) == body
        assert error.response.body_sha256 == hashlib.sha256(body).hexdigest()
        assert error.response.status == status and generation.health.last_http == (
            status,
            body,
        )
        assert error.response.port == generation.spec.ports.tiles
        assert len([c for c in commands.calls if HTTP_PROBE in c]) == 5
        assert generation.state == "failed" and error.record is None
        before = len(commands.calls)
        with pytest.raises(InvalidTransition):
            generation.start(guard())
        assert len(commands.calls) == before
        generation.stop(guard())


@pytest.mark.parametrize(
    "changes",
    [
        {"status": 200},
        {"status": True},
        {"port": True},
        {"port": 0},
        {"path": "//remote"},
        {"path": "/\n"},
        {"body_base64": "!"},
        {"body_sha256": "0" * 64},
        {"body_size_bytes": 0},
        {"schema_version": "map-startup-http-response/2"},
    ],
)
def test_bad_diagnostic_rejected_before_storage(changes: dict[str, Any]) -> None:
    original = MapHttpStartupFailure(
        12006, "/tile/1/1/1.png", 503, b"original"
    ).response
    with pytest.raises((ValueError, ValidationError)):
        MapStartupHttpResponse.model_validate({**original.model_dump(), **changes})


def test_complete_failed_start_record_is_bound_to_original_rpc_hash(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch)
    body = b"original private tile error\xff" * 20
    c.case.commands.http = [reply(200, b"ready")] * 4 + [reply(503, body)]
    try:
        with pytest.raises(SiteWorkerFailure) as caught:
            with enter(c.resource):
                raise AssertionError("failed start must not yield an instance")
        assert c.worker is not None and c.worker.tasks is None and c.worker.closed
        inputs = c.configuration.map_inputs
        assert inputs is not None
        path = Path(inputs.artifact_root) / "startup-http-failure.json"
        raw = path.read_bytes()
        record = MapStartupHttpFailureRecord.model_validate_json(raw)
        assert (
            record.scope == c.scope
            and record.instance_id == c.configuration.files.instance_id
        )
        assert (
            record.configuration_sha256
            == hashlib.sha256(c.configuration.model_dump_json().encode()).hexdigest()
        )
        assert record.writer == c.owner_guard.worker
        assert base64.b64decode(record.response.body_base64) == body
        error = caught.value.reply.error
        assert error is not None and error.type_name == "MapHttpStartupFailure"
        assert (
            error.reason_code
            == "MAP_STARTUP_HTTP_RECORD_" + hashlib.sha256(raw).hexdigest()
        )
        assert (
            path.stat().st_mode & 0o222 == 0 and inspect(c.resource).state == "closed"
        )
        assert (
            not c.sql.calls
            and len([r for r in c.case.commands.calls if HTTP_PROBE in r]) == 5
        )
        with pytest.raises(InvalidTransition):
            c.worker.start(guard())
        assert path.read_bytes() == raw
    finally:
        c.close_sockets()


@pytest.mark.parametrize("partial", [False, True])
def test_startup_and_publication_failures_preserve_first_and_all_cleanup(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, partial: bool
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch)
    c.case.commands.http = [reply(200, b"ready")] * 4 + [
        reply(503, b"failed native response")
    ]
    original = cast(Any, site_storage).write_once

    def broken(*args: Any, **kwargs: Any) -> Any:
        if partial:
            original(*args, **kwargs)
        raise OSError(errno.ENOSPC, "synthetic diagnostic save failure")

    monkeypatch.setattr(site_storage, "write_once", broken)
    try:
        with pytest.raises(SiteWorkerFailure) as caught:
            with enter(c.resource):
                raise AssertionError("failed publication must not yield an instance")
        error = caught.value.reply.error
        assert error is not None and error.type_name == "ExceptionGroup"
        assert [r.type_name for r in error.children] == [
            "MapHttpStartupFailure",
            "OSError",
        ]
        assert error.children[1].errno == errno.ENOSPC
        assert c.worker is not None and isinstance(
            c.worker.error, MapHttpStartupFailure
        )
        assert c.worker.error.record is None and c.worker.closed
        assert inspect(c.resource).state == "closed" and not c.sql.calls
        inputs = c.configuration.map_inputs
        assert inputs is not None
        path = Path(inputs.artifact_root) / "startup-http-failure.json"
        assert path.exists() is partial
    finally:
        c.close_sockets()
