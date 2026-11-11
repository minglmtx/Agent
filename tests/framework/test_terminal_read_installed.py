"""Actual installed readonly terminal worker over an independent review namespace."""

from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.plans.terminal_read_protocol import (
    ENTRY,
    MAX_PACKET,
    TerminalReadReply,
    encode_command,
    decode_command,
)
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.capture import require_reaped
from lab_generate_skill.bootstrap.terminal_read_bindings import (
    require_complete_terminal_bodies,
)
from lab_generate_skill.domain.terminal_read import (
    TerminalReadCommand,
    TerminalReadRequest,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from admin_navigation_terminal_fixtures import terminal_case
from state_read_fixtures import reader_case
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from test_admin_navigation_input import contracts as contracts
from test_slurm_commands import guard


def test_installed_terminal_read_has_no_namespace_writes_and_preserves_failed_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    installed_sources: InstalledFixture,
) -> None:
    (tmp_path / "terminal").mkdir()
    with terminal_case(
        tmp_path / "terminal", monkeypatch, contracts, current=True
    ) as c:
        request = TerminalReadRequest(
            terminal_ref=c.reference,
            contract=c.contract,
            initial=c.initial,
            operation=c.operation,
        )
        case = reader_case(
            tmp_path / "reader",
            c.store._blobs.parent,
            request.initial.prepared.scope.task,
            installed_sources,
        )
        before = {
            p.name: p.read_bytes() for p in (tmp_path / "reader/sessions").iterdir()
        }

        def invoke() -> tuple[TerminalReadCommand, TerminalReadReply]:
            with case.current.store.read_scope(case.controls.bind(case.operation)) as (
                scope,
                bounded,
            ):
                command = TerminalReadCommand(
                    scope=scope,
                    workspace_root=case.scope.workspace_root,
                    request=request,
                    purpose="retained_data",
                )
                packet = encode_command(command)
                assert decode_command(packet) == command
                capture = ProcessRunner(max_output_bytes=MAX_PACKET).run(
                    (str(installed_sources.executable), "-I", "-B", "-m", ENTRY),
                    bounded,
                    stdin_bytes=packet,
                )
                assert (
                    capture.complete and capture.returncode == 0
                ), capture.stderr.decode()
                ending = require_reaped(capture)
                reply = TerminalReadReply.model_validate_json(capture.stdout)
                assert reply.worker.process_id == ending.process_id
                return command, reply

        command, reply = invoke()
        assert reply.error is None and reply.bodies is not None
        assert reply.bodies.purpose == "retained_data"
        require_complete_terminal_bodies(reply.bodies, guard(30))
        assert reply.read_count >= reply.body_read_count == reply.unique_objects > 0
        with pytest.raises(OwnershipConflict):
            TerminalReadCommand.model_validate(
                command.model_copy(update={"purpose": "same_task"})
            )
        for raw in (
            b"",
            b"{}",
            b"[]",
            encode_command(command) + b"\n",
            b"x" * (MAX_PACKET + 1),
        ):
            with pytest.raises((ValueError, ValidationError)):
                decode_command(raw)
        # A failed readonly proof returns no bodies and does not poison the
        # unchanged original reader namespace or retry the missing operation.
        blob = (
            Path(case.scope.config.evidence_root)
            / "blobs"
            / request.terminal_ref.sha256
        )
        original = blob.read_bytes()
        blob.write_bytes(b"corrupt")
        _, failed = invoke()
        assert failed.error is not None and failed.bodies is None
        blob.write_bytes(original)
        assert case.current.store.state == "ready"
        assert before == {
            p.name: p.read_bytes() for p in (tmp_path / "reader/sessions").iterdir()
        }
