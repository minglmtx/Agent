"""Finite terminal handoff: real readers, exact bodies, live gates, no producers."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
import task_resource_owner_fixtures as owner_fixtures
from admin_navigation_terminal_fixtures import terminal_case
from task_actor_input_fixtures import fixed_task_source_inputs
from site_instance_fixtures import node_path as node_path
from test_admin_navigation_input import contracts as contracts
from test_slurm_commands import guard
from test_capture_initial_handoff import chain
from lab_generate_skill.bootstrap.terminal_read_binding import CompleteTerminalReads
from lab_generate_skill.bootstrap.terminal_read_bindings import (
    read_terminal_bodies,
    require_complete_terminal_bodies,
)
from lab_generate_skill.domain.terminal_read import (
    TerminalReadBodies,
    TerminalReadRequest,
    TerminalEvidenceBody,
)
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl


class LocalProof:
    """Explicit synchronous I/O double; no live namespace permission."""

    def __init__(self, store: EvidenceReader, fault: str = "none") -> None:
        self.store, self.fault = store, fault
        self.result: TerminalReadBodies | None = None
        self.reads = self.gates = 0
        self.revoked = False

    def check_current(self, control: OperationControl) -> None:
        control.checkpoint()
        self.gates += 1
        if self.revoked:
            raise PermissionError("Original terminal permission revoked")

    def read(
        self, request: TerminalReadRequest, control: OperationControl
    ) -> TerminalReadBodies:
        self.reads += 1
        self.check_current(control)
        if self.fault in {"cancel", "deadline"}:
            raise OperationStopped(
                "CANCELLED" if self.fault == "cancel" else "DEADLINE_EXCEEDED",
                request.operation.operation_id,
            )
        bodies = read_terminal_bodies(request, self.store, control)
        if self.fault == "missing":
            bodies = TerminalReadBodies.model_validate(
                bodies.model_copy(
                    update={
                        "bodies": tuple(
                            value
                            for value in bodies.bodies
                            if value.reference != bodies.bodies[-1].reference
                        )
                    }
                )
            )
        elif self.fault == "retained":
            bodies = bodies.model_copy(update={"purpose": "retained_data"})
        elif self.fault == "request":
            bodies = bodies.model_copy(
                update={
                    "request": request.model_copy(
                        update={
                            "operation": request.operation.model_copy(
                                update={"operation_id": "foreign"}
                            )
                        }
                    )
                }
            )
        self.result = bodies
        if self.fault == "revoked":
            self.revoked = True
        return bodies


@pytest.mark.parametrize("current", [False, True])
@pytest.mark.parametrize("negative", [False, True])
def test_admin_terminal_complete_original_bytes_and_no_repeated_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    current: bool,
    negative: bool,
) -> None:
    with terminal_case(
        tmp_path, monkeypatch, contracts, current=current, negative=negative
    ) as c:
        request = TerminalReadRequest(
            terminal_ref=c.reference,
            contract=c.contract,
            initial=c.initial,
            operation=c.operation,
        )
        proof = LocalProof(c.store)
        result = CompleteTerminalReads(proof).read(request, guard(30))
        assert result.request == request and len(result.bodies) > 10
        assert proof.reads == 1 and proof.gates == 2
        # Completeness is checked using returned bytes, never another CAS read.
        with monkeypatch.context() as proof_reads:
            proof_reads.setattr(
                c.store, "read", lambda *args, **kwargs: pytest.fail("old body reread")
            )
            require_complete_terminal_bodies(result, guard(30))
            missing = result.model_copy(update={"bodies": result.bodies[:-1]})
            with pytest.raises(EvidenceIntegrityError, match="omitted"):
                require_complete_terminal_bodies(missing, guard(30))
        body = result.bodies[0]
        with pytest.raises(EvidenceIntegrityError):
            TerminalEvidenceBody(
                reference=body.reference, json_text=body.json_text + " "
            )
        with pytest.raises(ValueError):
            TerminalReadBodies(request=request, bodies=(*result.bodies, body))


@pytest.mark.parametrize(
    "fault", ["none", "missing", "retained", "request", "revoked", "cancel", "deadline"]
)
def test_map_capture_judgment_handoff_and_original_cleanup(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    from lab_generate_skill.bootstrap.map_task_execution import (
        map_navigation_task_execution,
    )
    from lab_generate_skill.sites.map.tasks.navigation_capture_records import (
        NavigationCaptureRecords,
    )

    original = map_navigation_task_execution
    proofs: list[LocalProof] = []

    def compose(*args: Any, **kwargs: Any) -> Any:
        runtime = args[3]
        proof = LocalProof(runtime.evidence, fault)
        proofs.append(proof)
        kwargs["terminal_reads"] = CompleteTerminalReads(proof)
        return original(*args, **kwargs)

    monkeypatch.setattr(owner_fixtures, "map_navigation_task_execution", compose)
    with owner_fixtures.owned_task(
        node_path, monkeypatch, input_handoff=True, capture_initial_handoff=True
    ) as (c, r):
        fixed_task_source_inputs(c, r, monkeypatch)
        assert r.inputs is not None
        store = c.p.original.resource.evidence
        old_read = store.read
        denied_old: list[EvidenceRef] = []

        def read(
            reference: EvidenceRef, control: OperationControl | None = None
        ) -> bytes:
            result = proofs[0].result
            if c.bundle.capture.state.phase == "captured" and result is not None:
                if reference in {body.reference for body in result.bodies}:
                    denied_old.append(reference)
                    pytest.fail("Judgment reread a completed terminal dependency")
            return old_read(reference, control)

        monkeypatch.setattr(store, "read", read)
        if fault == "none":
            records = c.bundle.capture.records
            assert isinstance(records, NavigationCaptureRecords)
            verify = records.verify

            def verify_twice(*args: Any) -> None:
                verify(*args)
                with ThreadPoolExecutor(max_workers=1) as pool:
                    with pytest.raises(OwnershipConflict):
                        pool.submit(verify, *args).result()
                verify(*args)

            monkeypatch.setattr(c.bundle.capture.records, "verify", verify_twice)
        if fault == "none":
            result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert result.evaluation.status == "success"
            assert c.bundle.capture.state.phase == "captured"
            assert c.bundle.finalization.state.reset is not None
            assert c.bundle.finalization.state.reset.status == "safe"
            assert proofs[0].gates >= 4 and not denied_old
        else:
            with pytest.raises(TaskExecutionUnconfirmed) as caught:
                c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            expected = (
                EvidenceIntegrityError
                if fault == "missing"
                else (
                    PermissionError
                    if fault == "revoked"
                    else (
                        OperationStopped
                        if fault in {"cancel", "deadline"}
                        else OwnershipConflict
                    )
                )
            )
            assert any(isinstance(error, expected) for error in chain(caught.value))
            assert c.bundle.capture.state.phase == "quarantined"
        assert proofs[0].reads == c.native.loader.session.calls == 1
        assert not r.inputs.active and r.inputs.terminal_bodies is None
        browser = r.browser()
        assert browser is not None and browser.phase == "closed"


@pytest.mark.parametrize(
    "fault", ["owner", "attempt", "schema", "empty", "duplicate", "type"]
)
def test_terminal_declaration_rejects_invalid_or_foreign_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    fault: str,
) -> None:
    with terminal_case(tmp_path, monkeypatch, contracts, current=True) as c:
        request = TerminalReadRequest(
            terminal_ref=c.reference,
            contract=c.contract,
            initial=c.initial,
            operation=c.operation,
        )
        if fault in {"owner", "attempt"}:
            field = "owner_id" if fault == "owner" else "attempt_id"
            changed = request.model_copy(
                update={
                    "operation": request.operation.model_copy(update={field: "foreign"})
                }
            )
            with pytest.raises(OwnershipConflict):
                TerminalReadRequest.model_validate(changed)
        elif fault == "schema":
            with pytest.raises(OwnershipConflict):
                TerminalReadRequest.model_validate(
                    request.model_copy(
                        update={
                            "terminal_ref": request.terminal_ref.model_copy(
                                update={
                                    "content_schema": "map-navigation-terminal-selection/1"
                                }
                            )
                        }
                    )
                )
        elif fault == "empty":
            with pytest.raises(ValidationError):
                TerminalReadBodies(request=request, bodies=())
        elif fault == "type":
            with pytest.raises(ValidationError):
                TerminalReadBodies.model_validate([])
        else:
            result = read_terminal_bodies(request, c.store, guard(30))
            with pytest.raises(ValueError):
                TerminalReadBodies(
                    request=request, bodies=(*result.bodies, result.bodies[0])
                )
