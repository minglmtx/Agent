"""Actual fixed input/check children with original parent native-file semantics."""

from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.map_artifacts.state_input_transport import (
    MapStateInputsFailure,
)
from lab_generate_skill.adapters.map_artifacts.state_input_protocol import (
    MapStateInputsReply,
)
from lab_generate_skill.adapters.processes.capture import CommandCapture, CommandFailure
from lab_generate_skill.domain.errors import (
    OperationStopped,
    OwnershipConflict,
    InvalidTransition,
    EvidenceError,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from map_registered_worker_fixtures import RegisteredMapCase
from map_qualification_fixtures import qualified, restore
from map_navigation_group_cases import SOURCES
from map_state_input_fixtures import (
    input_case,
    CountNativeFiles,
    append_external_resolved_history,
)
from preparation_record_fixtures import put
from test_closed_source_read_faults import StopAfterReturn
from site_instance_fixtures import node_path as node_path
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from test_slurm_commands import guard


def test_installed_whole_graph_original_parent_files_and_unchanged_namespace(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    installed_sources: InstalledFixture,
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=SOURCES[0])
    try:
        with qualified(c, monkeypatch) as q:
            selected = restore(q)
            reset_ref = put(c.resource.evidence, selected)
            case = input_case(tmp_path / "reader", q, installed_sources)
            control = case.metadata.controls.bind(case.metadata.operation)
            expected_env = case.original.environment(
                q.environment,
                q.environment_ref,
                q.preparation.environment.operation,
                guard(60),
            )
            expected_reset = case.original.reset(selected, reset_ref, guard(60))
            before = {
                p.name: p.read_bytes() for p in (tmp_path / "reader/sessions").iterdir()
            }
            original_run = case.inputs.runner.run
            calls: list[tuple[str, ...]] = []

            def run(
                argv: tuple[str, ...],
                control: OperationControl,
                *,
                stdin_bytes: bytes | None = None,
            ) -> CommandCapture:
                calls.append(argv)
                return original_run(argv, control, stdin_bytes=stdin_bytes)

            monkeypatch.setattr(case.inputs.runner, "run", run)
            native = CountNativeFiles(case.checks.files)
            case.checks.files = native
            q.qualifications.checks = case.checks
            read = q.preparation.environment.operation.cleanup(
                "current-map-proof", now=datetime.now(timezone.utc), seconds=120
            )
            rights = q.authority.calls
            actual_env = q.qualifications.load_environment(
                q.environment_ref,
                q.preparation.publication.selection.environment_ref,
                read,
            )
            # The preparation publication uses this same original EnvironmentBaseline.
            assert actual_env == expected_env and q.authority.calls == rights + 1
            assert len(calls) == 2 and native.calls
            env_reply = case.inputs.last_inputs_reply
            assert (
                env_reply is not None and env_reply.error is None and env_reply.bodies
            )
            actual_reset = case.checks.reset(selected, reset_ref, control)
            assert actual_reset == expected_reset and len(calls) == 4
            assert case.inputs.last_check_reply is not None
            assert case.inputs.last_check_reply.read_count == 0
            reset_reply = case.inputs.last_inputs_reply
            assert reset_reply is not None
            assert before == {
                p.name: p.read_bytes() for p in (tmp_path / "reader/sessions").iterdir()
            }
            report = {
                "passed": True,
                "environment_and_reset_match_original": True,
                "original_parent_native_files_retained": True,
                "metadata_namespace_unchanged": True,
                "workers_per_proof": 2,
                "environment_graph_body_reads": env_reply.body_read_count,
                "environment_graph_unique_objects": env_reply.unique_objects,
                "reset_graph_body_reads": reset_reply.body_read_count,
                "actual_source_or_training_grant": False,
            }
            (
                Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
                / "map-state-inputs-installed.json"
            ).write_text(json.dumps(report, indent=2) + "\n")
    finally:
        c.close_sockets()


@pytest.mark.parametrize(
    "fault",
    [
        "cancel",
        "revoke",
        "request",
        "pid",
        "malformed",
        "unknown",
        "native_rights",
        "namespace_after_parent",
        "cancel_after_native",
    ],
)
def test_changed_live_boundary_or_partial_reply_never_returns_state(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    installed_sources: InstalledFixture,
    fault: str,
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=SOURCES[0])
    try:
        with qualified(c, monkeypatch) as q:
            case = input_case(tmp_path / "reader", q, installed_sources)
            control = case.metadata.controls.bind(case.metadata.operation)
            stop = StopAfterReturn(control)
            original_run = case.inputs.runner.run
            calls: list[tuple[str, ...]] = []

            def run(
                argv: tuple[str, ...],
                control: OperationControl,
                *,
                stdin_bytes: bytes | None = None,
            ) -> CommandCapture:
                calls.append(argv)
                capture = original_run(argv, control, stdin_bytes=stdin_bytes)
                if len(calls) != 1:
                    return capture
                if fault == "cancel":
                    stop.stopped = True
                elif fault == "revoke":
                    case.metadata.current.admission.stop_new_io()
                elif fault == "malformed":
                    capture = replace(capture, stdout=b"{}")
                elif fault == "unknown":
                    capture = replace(capture, termination=None)
                elif fault in ("request", "pid"):
                    reply = MapStateInputsReply.model_validate_json(capture.stdout)
                    reply = reply.model_copy(
                        update=(
                            {"request_sha256": "0" * 64}
                            if fault == "request"
                            else {
                                "worker": reply.worker.model_copy(
                                    update={"process_id": reply.worker.process_id + 1}
                                )
                            }
                        )
                    )
                    capture = replace(capture, stdout=reply.model_dump_json().encode())
                return capture

            monkeypatch.setattr(case.inputs.runner, "run", run)
            original_file = case.checks.files.read

            def native(descriptor: Any, request: Any, local: Any) -> bytes:
                if fault == "native_rights":
                    raise PermissionError("original Map file permission revoked")
                raw = original_file(descriptor, request, local)
                if fault == "cancel_after_native":
                    stop.stopped = True
                if fault == "namespace_after_parent":
                    path = next(
                        (tmp_path / "reader/sessions").glob("*.evidence-session.json")
                    )
                    append_external_resolved_history(path)
                return raw

            monkeypatch.setattr(case.checks.files, "read", native)
            with pytest.raises(
                (
                    EvidenceError,
                    OperationStopped,
                    OwnershipConflict,
                    InvalidTransition,
                    ValueError,
                    PermissionError,
                    CommandFailure,
                )
            ):
                case.checks.environment(
                    q.environment,
                    q.environment_ref,
                    q.preparation.environment.operation,
                    stop,
                )
            assert len(calls) == (2 if fault == "namespace_after_parent" else 1)
            assert case.inputs.quarantined == (fault == "unknown")
            if fault == "unknown":
                with pytest.raises(MapStateInputsFailure):
                    case.checks.environment(
                        q.environment,
                        q.environment_ref,
                        q.preparation.environment.operation,
                        control,
                    )
                assert len(calls) == 1
    finally:
        c.close_sockets()


@pytest.mark.parametrize("fault", ["missing", "corrupt"])
def test_fresh_invocation_reopens_original_CAS_and_never_uses_previous_bodies(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    installed_sources: InstalledFixture,
    fault: str,
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=SOURCES[0])
    try:
        with qualified(c, monkeypatch) as q:
            case = input_case(tmp_path / "reader", q, installed_sources)
            control = case.metadata.controls.bind(case.metadata.operation)
            case.checks.environment(
                q.environment,
                q.environment_ref,
                q.preparation.environment.operation,
                control,
            )
            path = (
                Path(case.metadata.scope.config.evidence_root)
                / "blobs"
                / q.environment.spec_ref.sha256
            )
            if fault == "missing":
                path.unlink()
            else:
                path.write_bytes(b"corrupt")
            with pytest.raises(MapStateInputsFailure):
                case.checks.environment(
                    q.environment,
                    q.environment_ref,
                    q.preparation.environment.operation,
                    control,
                )
            assert not case.inputs.quarantined
            assert case.inputs.last_check_reply is None
    finally:
        c.close_sockets()
