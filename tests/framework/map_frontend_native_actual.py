"""Actual owned native frontend stop/clear/replacement/HTTP/state seam."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import traceback
from typing import Any
import pytest
from lab_generate_skill.adapters.processes.capture import retained_capture
from map_frontend_native_fixture import NativeFrontendFixture, FixtureControls, PROGRAM
from test_slurm_commands import guard


def test_native_frontend_fixture_preflight_has_explicit_short_local_grace() -> None:
    assert PROGRAM.count("TCPServer.new('127.0.0.1', port)") == 1
    assert "['graceful', 'forced']" in PROGRAM and "Content-Length" in PROGRAM
    assert FixtureControls().bind(guard(120), "frontend_grace").checkpoint() <= 0.25
    assert FixtureControls().bind(guard(120), "frontend_force").checkpoint() <= 10
    assert FixtureControls().bind(guard(0.1), "frontend_grace").checkpoint() <= 0.1


@pytest.mark.parametrize("mode", ["graceful", "forced"])
def test_actual_original_image_frontend_generation_reset_and_namespace_closure(
    mode: str,
) -> None:
    root = Path(tempfile.mkdtemp(prefix="lab-map-frontend-native-", dir="/tmp"))
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    fixture = NativeFrontendFixture(root)
    primary: BaseException | None = None
    facts: dict[str, Any] = dict(
        engineering_only=True,
        registered_worker=False,
        actual_rails=False,
        actual_map_website=False,
        actual_actor=False,
        paid_calls=0,
        state_sql_synthetic=True,
        native_images_loaded=["web"],
        original_root=str(root),
        mode=mode,
        production_grace_seconds=30,
        fixture_grace_seconds=0.25,
        program_sha256=hashlib.sha256(PROGRAM.encode()).hexdigest(),
    )
    closed_namespaces = []
    try:
        reset = fixture.initialize(mode, guard(120))
        assert fixture.services is not None
        old = fixture.services.records[0]
        cleared = reset.begin(guard(60))
        assert cleared.stopped.forced_namespace == (mode == "forced")
        if mode == "graceful":
            assert cleared.stopped.master.returncode == 0
        assert cleared.preserved_sprockets
        assert old.retirement == cleared.stopped
        closed_namespaces.append(cleared.stopped.namespace.model_dump(mode="json"))
        result = reset.resume(guard(120))
        assert result.before_sha256 == result.after_sha256
        assert result.frontend != cleared.stopped.namespace.original
        assert result.endpoint == fixture.spec.endpoint
        assert len(fixture.services.records) == 2
        assert old.argv == fixture.services.records[-1].argv
        app = Path(fixture.spec.inputs.node_tree("frontend"))
        assert (
            app / "tmp/cache/assets/sprockets/original"
        ).read_bytes() == b"original compiled cache"
        assert not (app / "tmp/cache/old-session").exists() and not list(
            (app / "tmp/pids").iterdir()
        )
        facts["resumed"] = result.model_dump(mode="json")
        assert reset.guard.initial is not None
        facts["initial_persistent"] = reset.guard.initial.persistent.model_dump(
            mode="json"
        )
        facts["synthetic_sql_calls"] = len(fixture.sql.calls)
    except BaseException as error:
        primary = error
        (output / f"map-frontend-native-{mode}-failure.txt").write_text(
            "".join(traceback.format_exception(error))
        )
        capture = retained_capture(error)
        if capture is not None:
            (output / f"map-frontend-native-{mode}-stdout.bin").write_bytes(
                capture.stdout
            )
            (output / f"map-frontend-native-{mode}-stderr.bin").write_bytes(
                capture.stderr
            )
        raise
    finally:
        cleanup: list[BaseException] = []
        services = fixture.services
        if services is not None:
            try:
                if primary is None:
                    stopped = services.retire_frontend(guard(60))
                    assert stopped.generation == 2 and stopped.forced_namespace == (
                        mode == "forced"
                    )
                    if mode == "graceful":
                        assert stopped.master.returncode == 0
                    closed_namespaces.append(stopped.namespace.model_dump(mode="json"))
                    facts["final_frontend_stop"] = stopped.model_dump(mode="json")
                elif (
                    "rails_server" in services.active
                    and services.active["rails_server"].pin is not None
                ):
                    closed = services.stop_namespace("rails_server", guard(20))
                    closed_namespaces.append(closed.model_dump(mode="json"))
            except BaseException as error:
                cleanup.append(error)
            try:
                exits = services.stop(guard(30))
                facts["original_service_exits"] = [
                    e.model_dump(mode="json") for e in exits
                ]
                assert all(e.state == "reaped" for e in exits)
            except BaseException as error:
                cleanup.append(error)
            for record in services.records:
                log = (
                    Path(fixture.spec.inputs.files.log_root)
                    / f"{record.name}-{record.number}"
                    / (record.name + ".log")
                )
                if log.exists():
                    (
                        output / f"map-frontend-native-{mode}-{record.number}.log"
                    ).write_bytes(log.read_bytes())
        try:
            if primary is None and not cleanup:
                assert fixture.lease is not None and len(closed_namespaces) == 2
                fixture.lease.release(guard())
                facts["original_lease_released_after_namespace_closure"] = True
        except BaseException as error:
            cleanup.append(error)
        facts["closed_namespaces"] = closed_namespaces
        facts["cleanup_errors"] = [repr(e) for e in cleanup]
        facts["passed"] = primary is None and not cleanup
        facts["root_retained"] = not facts["passed"]
        if facts["passed"]:
            shutil.rmtree(root)
        (output / f"map-frontend-native-{mode}-result.json").write_text(
            json.dumps(facts, indent=2) + "\n"
        )
        if cleanup:
            raise BaseExceptionGroup(
                "Native frontend primary and cleanup failures",
                ([primary] if primary is not None else []) + cleanup,
            ) from None
