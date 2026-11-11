"""Production preparation through original fixed RPC; all physical rights fake."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.preparation import EnvironmentBaseline
import json
import pytest
from lab_generate_skill.adapters.sites.task_preparation import (
    TaskPreparationUnconfirmed,
)
from lab_generate_skill.bootstrap.map_task_preparation import map_task_preparation
from lab_generate_skill.domain.task_preparation import SiteTaskPrepared
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from map_task_preparation_port_fixtures import MapPreparationPortCase, preparation_case
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.fixture
def p(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[MapPreparationPortCase]:
    with preparation_case(node_path, monkeypatch) as value:
        yield value


def test_original_registered_snapshot_environment_prepare_and_repeat(
    p: MapPreparationPortCase,
) -> None:
    assert p.acquire() and not p.requests
    result = p.prepare()
    assert [request.action for request in p.requests] == ["snapshot", "prepare"]
    receipt = SiteTaskPrepared.model_validate_json(
        p.original.resource.evidence.read(result[0])
    )
    assert receipt == p.preparation.state.result
    assert receipt.scope == p.declaration.scope
    prepared = p.preparation.records.load(
        receipt.publication, p.declaration.prepare_operation
    )
    assert (
        prepared.scope == p.declaration.scope
        and prepared.recovery_ref == p.reset.task_recovery_ref
    )
    assert p.requests[1].snapshot_ref == receipt.snapshot_ref
    assert json.loads(p.original.resource.evidence.read(receipt.snapshot_ref))[
        "request"
    ] == p.requests[0].model_dump(mode="json")
    assert p.preparation.state.environment is not None
    assert p.preparation.state.environment.checks.status == "pass"
    with pytest.raises(DispatchAlreadyCommitted):
        p.acquire()
    with pytest.raises(DispatchAlreadyCommitted):
        p.prepare()
    assert len(p.requests) == 2


def test_prepare_without_original_binding_never_dispatches(
    p: MapPreparationPortCase,
) -> None:
    with pytest.raises(DispatchAlreadyCommitted):
        p.prepare()
    assert not p.requests


def test_required_source_authority_denial_has_no_native_task(
    p: MapPreparationPortCase,
) -> None:
    p.authority.denied = True
    with pytest.raises(TaskPreparationUnconfirmed) as failed:
        p.acquire()
    assert isinstance(failed.value.primary, PermissionError)
    assert not p.requests
    with pytest.raises(DispatchAlreadyCommitted):
        p.acquire()


@pytest.mark.parametrize("phase", ["snapshot", "prepare"])
def test_unknown_native_call_retains_intent_and_never_repeats(
    p: MapPreparationPortCase, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    p.acquire()
    original = p.site.tasks.execute_task
    called: list[SiteTaskRequest] = []

    def fail(request: SiteTaskRequest, *, control: OperationControl) -> SiteTaskResult:
        called.append(request)
        if request.action == phase:
            raise TimeoutError("controlled unknown response")
        return original(request, control=control)

    monkeypatch.setattr(p.site.tasks, "execute_task", fail)
    with pytest.raises(TaskPreparationUnconfirmed) as failed:
        p.prepare()
    assert failed.value.phase == phase and isinstance(
        failed.value.primary, TimeoutError
    )
    assert failed.value.references
    expected = ["snapshot"] if phase == "snapshot" else ["snapshot", "prepare"]
    assert [x.action for x in called] == expected
    with pytest.raises(DispatchAlreadyCommitted):
        p.prepare()
    assert [x.action for x in called] == expected


@pytest.mark.parametrize("fault", ["digest", "json", "schema", "request"])
def test_invalid_snapshot_response_keeps_complete_return_and_blocks_prepare(
    p: MapPreparationPortCase, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    p.acquire()
    original = p.site.tasks.execute_task

    def corrupt(
        request: SiteTaskRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        value = original(request, control=control)
        if fault == "digest":
            return value.model_copy(update={"request_sha256": "0" * 64})
        if fault == "json":
            return value.model_copy(update={"private_result": "{bad-json"})
        data = json.loads(value.private_result)
        data["schema_version" if fault == "schema" else "request"] = "invalid"
        return value.model_copy(update={"private_result": json.dumps(data)})

    monkeypatch.setattr(p.site.tasks, "execute_task", corrupt)
    with pytest.raises(TaskPreparationUnconfirmed) as failed:
        p.prepare()
    assert [x.action for x in p.requests] == ["snapshot"]
    assert (
        failed.value.snapshot_result is not None and failed.value.snapshot_ref is None
    )
    assert any(
        ref.content_schema == "site-task-result/1" for ref in failed.value.references
    )


@pytest.mark.parametrize("commit", [False, True])
def test_snapshot_publication_failure_keeps_result_and_does_not_prepare(
    p: MapPreparationPortCase, monkeypatch: pytest.MonkeyPatch, commit: bool
) -> None:
    p.acquire()
    store = p.original.resource.evidence
    original = store.put

    def failed(
        data: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        if metadata.content_schema == p.declaration.snapshot_schema:
            if commit:
                original(data, metadata, control=control)
            raise OSError("snapshot publication lost acknowledgement")
        return original(data, metadata, control=control, exchange_id=exchange_id)

    monkeypatch.setattr(store, "put", failed)
    with pytest.raises(TaskPreparationUnconfirmed) as error:
        p.prepare()
    assert error.value.snapshot_result is not None and error.value.snapshot_ref is None
    assert error.value.candidates and [r.action for r in p.requests] == ["snapshot"]
    if commit:
        assert (
            store.read(error.value.candidates[0])
            == error.value.snapshot_result.private_result.encode()
        )
    with pytest.raises(DispatchAlreadyCommitted):
        p.prepare()


def test_partial_prepared_publication_preserves_original_candidate_ref(
    p: MapPreparationPortCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    p.acquire()
    store = p.original.resource.evidence
    original = store.put

    def fail(
        data: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        if metadata.content_schema == "prepared-task/1":
            raise OSError("controlled second record failure")
        return original(data, metadata, control=control, exchange_id=exchange_id)

    monkeypatch.setattr(store, "put", fail)
    with pytest.raises(TaskPreparationUnconfirmed) as error:
        p.prepare()
    assert error.value.phase == "publication" and error.value.prepare_result is not None
    assert [x.action for x in p.requests] == ["snapshot", "prepare"]
    assert any(
        ref.content_schema == "preparation-receipt/1" for ref in error.value.references
    )
    with pytest.raises(DispatchAlreadyCommitted):
        p.prepare()


def test_cancellation_after_snapshot_keeps_native_return_and_stops_prepare(
    p: MapPreparationPortCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    p.acquire()
    cancelled = False
    original = p.site.tasks.execute_task

    class Control:
        def checkpoint(self) -> float:
            if cancelled:
                raise OperationStopped("CANCELLED", "task.preparing")
            return 1.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    def returned(
        request: SiteTaskRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        nonlocal cancelled
        result = original(request, control=control)
        cancelled = True
        return result

    monkeypatch.setattr(p.site.tasks, "execute_task", returned)
    with pytest.raises(TaskPreparationUnconfirmed) as failed:
        p.preparation.prepare(p.plan, p.operation("preparing"), Control())
    assert isinstance(failed.value.primary, OperationStopped)
    assert failed.value.snapshot_result is not None
    assert p.preparation.state.snapshot_result_ref in failed.value.references
    assert [r.action for r in p.requests] == ["snapshot"]
    with pytest.raises(DispatchAlreadyCommitted):
        p.prepare()


@pytest.mark.parametrize(
    "fault", ["scope", "spec", "allocation", "operation", "coverage", "failed"]
)
def test_wrong_environment_never_reaches_prepare(
    p: MapPreparationPortCase, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    p.acquire()
    original = p.preparation.qualifications.load_environment

    def wrong(
        selection_ref: EvidenceRef, reference: EvidenceRef, operation: OperationContext
    ) -> EnvironmentBaseline:
        value = original(selection_ref, reference, operation)
        if fault == "scope":
            return value.model_copy(
                update={
                    "scope": value.scope.model_copy(update={"attempt_id": "foreign"})
                }
            )
        if fault == "spec":
            return value.model_copy(
                update={"spec_ref": p.declaration.private_input_ref}
            )
        if fault == "allocation":
            return value.model_copy(
                update={
                    "allocation": value.allocation.model_copy(
                        update={"allocation_id": "foreign"}
                    )
                }
            )
        if fault == "operation":
            return value.model_copy(
                update={
                    "operation": value.operation.model_copy(
                        update={"operation_id": "foreign"}
                    )
                }
            )
        checks = value.checks.model_copy(
            update=(
                {"required": ()}
                if fault == "coverage"
                else {
                    "checks": (
                        value.checks.checks[0].model_copy(update={"status": "fail"}),
                        *value.checks.checks[1:],
                    )
                }
            )
        )
        return value.model_copy(update={"checks": checks})

    monkeypatch.setattr(p.preparation.qualifications, "load_environment", wrong)
    with pytest.raises(TaskPreparationUnconfirmed) as failed:
        p.prepare()
    assert failed.value.phase == "environment" and failed.value.snapshot_ref is not None
    assert isinstance(failed.value.primary, OwnershipConflict)
    assert [r.action for r in p.requests] == ["snapshot"]


@pytest.mark.parametrize("fault", ["private", "contract"])
def test_changed_original_private_or_contract_rejected_before_snapshot(
    p: MapPreparationPortCase, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    from lab_generate_skill.policies.task_preparation import (
        require_declared_preparation,
    )

    declaration = p.declaration
    plan = p.plan
    if fault == "private":
        declaration = declaration.model_copy(
            update={"private_input_ref": declaration.task_binding_ref}
        )
        # Native input may be an envelope, so byte relation belongs to the
        # mandatory native codec. Keep this exact corrupt reference rejected
        # there, before any request is physically dispatched.
        from pydantic import ValidationError
        from lab_generate_skill.domain.lifecycle import RecoveryPlan
        from lab_generate_skill.sites.map.tasks.native_request_rules import (
            NavigationNativeRequestChecks,
        )

        store = p.original.resource.evidence
        request = SiteTaskRequest(
            task=declaration.scope.task,
            binding_ref=declaration.task_binding_ref,
            operation=declaration.snapshot_operation,
            action="snapshot",
            private_input=store.read(declaration.private_input_ref).decode(),
        )
        recovery = RecoveryPlan.model_validate_json(
            store.read(p.reset.task_recovery_ref)
        )
        environment = RecoveryPlan.model_validate_json(
            store.read(p.reset.environment_recovery_ref)
        )
        with pytest.raises(ValidationError):
            NavigationNativeRequestChecks().verify_inputs(
                p.original.resource.spec.configuration,
                request,
                p.source.native.binding,
                recovery,
                environment,
                None,
                None,
                guard(30),
            )
        assert not p.requests
        return
    else:
        plan = plan.model_copy(
            update={
                "evaluation": plan.evaluation.model_copy(
                    update={"task_contract_ref": declaration.site_spec_ref}
                )
            }
        )
    n = p.source.native
    with pytest.raises(OwnershipConflict, match="public/private task/baseline"):
        require_declared_preparation(
            plan, declaration, p.reset, p.original.resource.spec, n.binding
        )
    assert not p.requests


@pytest.mark.parametrize("invalid", [None, "", [], 1, True])
def test_invalid_declaration_and_missing_authority_rejected(
    p: MapPreparationPortCase, invalid: Any
) -> None:
    from pydantic import ValidationError
    from lab_generate_skill.domain.task_preparation import SiteTaskPreparationPlan

    with pytest.raises((ValidationError, TypeError, ValueError)):
        SiteTaskPreparationPlan.model_validate(invalid)
    invalid_authority: Any = None
    with pytest.raises(ValueError, match="mandatory"):
        map_task_preparation(
            p.plan,
            p.declaration,
            p.original.resource.spec,
            p.site,
            p.original.resource.journal,
            p.original.resource.evidence,
            p.original.resource.controls,
            p.source.native.bindings,
            invalid_authority,
        )
    assert not p.requests
