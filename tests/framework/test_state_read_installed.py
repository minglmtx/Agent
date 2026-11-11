"""Actual fixed worker, pure original state algorithms, live original read gates."""

from dataclasses import replace
import json
import os
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.plans.state_read_checks import StateReadFailure
from lab_generate_skill.adapters.plans.state_read_protocol import StateReadReply
from lab_generate_skill.domain.errors import (
    OperationStopped,
    InvalidTransition,
    OwnershipConflict,
)
from lab_generate_skill.domain.state_read import StateReadCommand
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.capture import CommandCapture, CommandFailure
from admin_navigation_state_fixtures import qualified
from state_read_fixtures import reader_case
from test_closed_source_read_faults import StopAfterReturn
from test_admin_navigation_input import contracts as contracts
from site_instance_fixtures import node_path as node_path
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from test_slurm_commands import guard


def test_installed_environment_and_reset_match_original_with_fresh_authority(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    installed_sources: InstalledFixture,
) -> None:
    with qualified(tmp_path, node_path, monkeypatch, contracts) as c:
        selection, reset = c["environment"], c["reset"]
        original = c["records"].checks
        expected = original.environment(
            selection, c["selection_ref"], c["operation"], guard()
        )
        expected_reset = original.reset(reset, c["reset_ref"], guard())
        case = reader_case(
            tmp_path / "reader",
            c["store"]._blobs.parent,
            selection.scope.task,
            installed_sources,
        )
        before = {
            p.name: p.read_bytes() for p in (tmp_path / "reader/sessions").iterdir()
        }
        c["records"].checks = case.checks
        calls = len(c["authority"].calls)
        actual = c["records"].load_environment(
            c["selection_ref"], c["environment_ref"], c["operation"]
        )
        assert actual == expected and len(c["authority"].calls) == calls + 1
        reply = case.checks.last_reply
        assert reply is not None and reply.environment == expected
        assert reply.read_count >= reply.body_read_count >= reply.unique_objects > 0
        checked_reset = case.checks.reset(
            reset, c["reset_ref"], case.controls.bind(case.operation)
        )
        assert checked_reset == expected_reset
        assert case.current.store.state == "ready" and not case.checks.quarantined
        capture = case.checks.last_capture
        assert capture is not None and capture.termination is not None
        assert capture.termination.state == "reaped"
        assert before == {
            p.name: p.read_bytes() for p in (tmp_path / "reader/sessions").iterdir()
        }
        c["authority"].denied = True
        last = case.checks.last_capture
        with pytest.raises(PermissionError):
            c["records"].load_environment(
                c["selection_ref"], c["environment_ref"], c["operation"]
            )
        assert case.checks.last_capture is last
        (
            Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "state-read-installed.json"
        ).write_text(
            json.dumps(
                {
                    "passed": True,
                    "same_original_environment_and_reset": True,
                    "original_parent_state_authority_retained": True,
                    "fixed_child_reaped": True,
                    "metadata_history_unchanged": True,
                    "environment_logical_reads": reply.read_count,
                    "environment_body_reads": reply.body_read_count,
                    "original_site_permission_is_synthetic_fixture": True,
                    "actual_site_model_claim_or_training_grant": False,
                },
                indent=2,
            )
            + "\n"
        )


@pytest.mark.parametrize("fault", ["missing", "corrupt"])
def test_later_proof_reopens_missing_or_corrupt_original_bytes(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    installed_sources: InstalledFixture,
    fault: str,
) -> None:
    with qualified(tmp_path, node_path, monkeypatch, contracts) as c:
        selection = c["environment"]
        case = reader_case(
            tmp_path / "reader",
            c["store"]._blobs.parent,
            selection.scope.task,
            installed_sources,
        )
        control = case.controls.bind(case.operation)
        case.checks.environment(selection, c["selection_ref"], c["operation"], control)
        path = (
            Path(case.scope.config.evidence_root)
            / "blobs"
            / selection.snapshot_ref.sha256
        )
        if fault == "missing":
            path.unlink()
        else:
            path.write_bytes(b"corrupt")
        with pytest.raises(StateReadFailure):
            case.checks.environment(
                selection, c["selection_ref"], c["operation"], control
            )
        assert (
            case.checks.last_reply is not None
            and case.checks.last_reply.error is not None
        )
        assert (
            case.checks.last_reply.environment is None and not case.checks.quarantined
        )


@pytest.mark.parametrize(
    "fault", ["cancel", "revoke", "request", "pid", "malformed", "unknown"]
)
def test_post_child_failure_never_returns_facts_or_replays(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    installed_sources: InstalledFixture,
    fault: str,
) -> None:
    with qualified(tmp_path, node_path, monkeypatch, contracts) as c:
        selection = c["environment"]
        case = reader_case(
            tmp_path / "reader",
            c["store"]._blobs.parent,
            selection.scope.task,
            installed_sources,
        )
        original = case.checks.runner.run
        stop = StopAfterReturn(case.controls.bind(case.operation))
        calls = []

        def run(
            argv: tuple[str, ...],
            control: OperationControl,
            *,
            stdin_bytes: bytes | None = None,
        ) -> CommandCapture:
            calls.append(argv)
            capture = original(argv, control, stdin_bytes=stdin_bytes)
            if fault == "cancel":
                stop.stopped = True
            elif fault == "revoke":
                case.current.admission.stop_new_io()
            elif fault == "malformed":
                capture = replace(capture, stdout=b"{}")
            elif fault == "unknown":
                capture = replace(capture, termination=None)
            else:
                reply = StateReadReply.model_validate_json(capture.stdout)
                if fault == "request":
                    reply = reply.model_copy(update={"request_sha256": "0" * 64})
                else:
                    reply = reply.model_copy(
                        update={
                            "worker": reply.worker.model_copy(
                                update={"process_id": reply.worker.process_id + 1}
                            )
                        }
                    )
                capture = replace(capture, stdout=reply.model_dump_json().encode())
            return capture

        monkeypatch.setattr(case.checks.runner, "run", run)
        with pytest.raises(
            (
                OperationStopped,
                InvalidTransition,
                OwnershipConflict,
                ValueError,
                CommandFailure,
            )
        ):
            case.checks.environment(selection, c["selection_ref"], c["operation"], stop)
        assert len(calls) == 1
        assert case.checks.quarantined == (fault == "unknown")
        if fault == "unknown":
            with pytest.raises(StateReadFailure):
                case.checks.environment(
                    selection,
                    c["selection_ref"],
                    c["operation"],
                    case.controls.bind(case.operation),
                )
            assert len(calls) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"site": "map"},
        {"family": "product_description"},
        {"contract_version": 2},
        {"split": "test"},
    ],
)
def test_unsupported_contract_refused_before_child(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    installed_sources: InstalledFixture,
    change: dict[str, Any],
) -> None:
    with qualified(tmp_path, node_path, monkeypatch, contracts) as c:
        selection = c["environment"]
        case = reader_case(
            tmp_path / "reader",
            c["store"]._blobs.parent,
            selection.scope.task,
            installed_sources,
        )
        case.checks.task = case.checks.task.model_copy(update=change)
        with pytest.raises(ValueError):
            case.checks.environment(
                selection,
                c["selection_ref"],
                c["operation"],
                case.controls.bind(case.operation),
            )
        assert case.checks.last_capture is None


def test_group_environment_and_reset_use_original_capture_codec_in_fixed_worker(
    tmp_path: Path,
    node_path: Path,
    installed_sources: InstalledFixture,
) -> None:
    from gitlab_group_qualification_fixtures import (
        qualified as group_qualified,
        restore,
    )
    from gitlab_group_preparation_fixtures import put
    from lab_generate_skill.domain.lifecycle import AllocationToken, ClosureReceipt
    from lab_generate_skill.bootstrap.gitlab_group_capture import load_group_capture
    from lab_generate_skill.sites.gitlab.tasks.group_state_checks import (
        GroupStateChecks,
    )

    with group_qualified(tmp_path / "facts", node_path) as c:
        p = c.preparation
        operation = p.inputs.environment.operation
        expected = GroupStateChecks(p.store, load_group_capture).environment(
            c.environment, c.environment_ref, operation, guard()
        )
        assert p.inputs.request.operation.recovery_ref is not None
        token = AllocationToken(
            allocation_id="synthetic-browser",
            owner=c.environment.scope.owner,
            scope="attempt",
            attempt_id=c.environment.scope.attempt_id,
            resource_kind="browser",
            expected_resource_id="synthetic-browser",
            provider_id="fixed-browser-worker",
            provider_version="3",
            recovery_ref=p.inputs.request.operation.recovery_ref,
        )
        closure = ClosureReceipt(
            token=token,
            operation_id="original-close",
            status="closed",
            evidence=(c.environment.spec_ref,),
        )
        restored = restore(c, (token,), (put(p.store, closure),))
        restored_ref = put(p.store, restored)
        expected_reset = GroupStateChecks(p.store, load_group_capture).reset(
            restored, restored_ref, guard()
        )
        case = reader_case(
            tmp_path / "reader",
            p.store._blobs.parent,
            c.environment.scope.task,
            installed_sources,
        )
        actual = case.checks.environment(
            c.environment,
            c.environment_ref,
            operation,
            case.controls.bind(case.operation),
        )
        assert actual == expected
        assert (
            case.checks.last_reply is not None
            and case.checks.last_reply.environment == expected
        )
        assert (
            case.checks.reset(
                restored, restored_ref, case.controls.bind(case.operation)
            )
            == expected_reset
        )
