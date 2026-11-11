"""Current native ports/CAS/owner; explicit synthetic physical/source rights."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from lab_generate_skill.adapters.sites.task_finalization import RecordedTaskFinalization
from lab_generate_skill.bootstrap.map_task_finalization import map_task_finalization
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import ClosureReceipt, OperationContext
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeIntent
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.task_finalization import (
    TaskFinalizationPlan,
    UnstartedTaskBrowser,
)
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    ClosedTaskResources,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from map_site_engineering_authority import MapEngineeringAuthority
from preparation_record_fixtures import put
from task_capture_port_fixtures import CapturePortCase
from map_task_preparation_port_fixtures import MapPreparationPortCase


class UnitFinalizationAuthority:
    def __init__(
        self, preparation: MapPreparationPortCase, *, current_native: bool = False
    ) -> None:
        self.preparation, self.denied = preparation, False
        self.current_native = current_native
        self.finalizer: RecordedTaskFinalization | None = None
        self.calls: list[OperationContext] = []

    def verify(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskFinalizationPlan,
        references: tuple[EvidenceRef, ...],
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.calls.append(operation)
        if self.denied:
            raise PermissionError("Synthetic original cleanup permission denied")
        p = self.preparation
        assert plan == p.plan and declaration.scope == p.reset.scope
        assert operation.mode == "cleanup"
        f = self.finalizer
        if (
            f is not None
            and f.state.restore_request is not None
            and operation == f.state.restore_request.operation
        ):
            ref = f.state.restore_request_ref
            assert ref is not None and ref in references
            assert (
                p.original.resource.evidence.read(ref, control)
                == f.state.restore_request.model_dump_json().encode()
            )
            if self.current_native:
                # Current OriginalTaskNativeAuthority consumes this exact
                # persisted request and checks recovery/source/current stages.
                # No legacy per-request grant may replace that supplier.
                assert f.preparation is p.preparation
                return
            authority = p.original.resource.authority
            assert isinstance(authority, MapEngineeringAuthority)
            # Re-reading the same grant is not another dispatch or intent.
            old = authority.task_intents.get(operation.operation_id)
            assert old is None or old == ref
            authority.task_intents[operation.operation_id] = ref


class UnitUnstartedAuthority:
    def __init__(self, case: CapturePortCase) -> None:
        self.case, self.denied, self.calls = case, False, 0

    def close_unstarted(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskFinalizationPlan,
        observed: UnstartedTaskBrowser,
        observed_ref: EvidenceRef,
        operation: OperationContext,
        control: OperationControl,
    ) -> ClosureReceipt:
        control.checkpoint()
        self.calls += 1
        c = self.case
        assert (
            c.initial.backend.engines == []
            and c.initial.backend.resource.channels == []
        )
        assert c.initial.browser.phase == "new" and c.initial.browser.manager is None
        assert observed.token == c.initial.preparation.reset.attempt_allocations[0]
        assert (
            c.initial.preparation.original.resource.evidence.read(observed_ref, control)
            == observed.model_dump_json().encode()
        )
        if self.denied:
            raise PermissionError(
                "Synthetic non-start premise not independently authorized"
            )
        return ClosureReceipt(
            token=observed.token,
            operation_id=operation.operation_id,
            status="closed",
            evidence=(observed_ref,),
        )


class UnitResumeAuthority:
    def __init__(self, preparation: MapPreparationPortCase) -> None:
        self.preparation, self.denied, self.calls = preparation, False, 0
        self.finalizer: RecordedTaskFinalization | None = None

    def verify_resume(
        self,
        configuration: SiteWorkerConfiguration,
        request: SiteResumeRequest,
        intent_ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if self.denied:
            raise PermissionError("Synthetic original resume permission denied")
        self.calls += 1
        p, f = self.preparation, self.finalizer
        assert f is not None and f.state.closed is not None
        assert configuration == p.original.resource.spec.configuration
        assert (
            request == f.state.resume_request
            and request.restore_result_ref == f.state.restore_result_ref
        )
        intent = SiteResumeIntent.model_validate_json(
            p.original.resource.evidence.read(intent_ref, control)
        )
        assert (
            intent.request == request
            and intent.configuration_sha256
            == hashlib.sha256(configuration.model_dump_json().encode()).hexdigest()
        )
        assert f.state.restore_result is not None
        assert (
            p.original.resource.evidence.read(request.restore_result_ref, control)
            == f.state.restore_result.model_dump_json().encode()
        )
        assert f.state.closed.closure_refs and all(
            c.status == "closed" for c in f.state.closed.closures
        )


@dataclass
class FinalizationPortCase:
    current: CapturePortCase
    finalizer: RecordedTaskFinalization
    authority: UnitFinalizationAuthority
    unstarted: UnitUnstartedAuthority
    resume: UnitResumeAuthority
    closed: ClosedTaskResources | None = None
    operations: dict[str, OperationContext] = field(default_factory=dict)

    def operation(self, name: str) -> OperationContext:
        if name in self.operations:
            return self.operations[name]
        plan = self.current.initial.preparation.plan
        operation = plan.operation.cleanup(
            "task-finalization-" + name,
            now=datetime.now(timezone.utc),
            seconds=plan.cleanup_seconds,
        )
        self.operations[name] = operation
        return operation

    def close(self) -> ClosedTaskResources:
        p = self.current.initial.preparation
        op = self.operation("closing")
        self.closed = self.finalizer.close(
            p.plan, p.reset, op, p.original.resource.controls.bind(op)
        )
        return self.closed

    def restore(self) -> EvidenceRef:
        assert self.closed is not None
        p = self.current.initial.preparation
        op = self.operation("restoring")
        return self.finalizer.restore(
            p.plan, self.closed, op, p.original.resource.controls.bind(op)
        )


def bind_finalization(case: CapturePortCase) -> FinalizationPortCase:
    p, browser = case.initial.preparation, case.initial.browser
    d = TaskFinalizationPlan(
        scope=p.reset.scope,
        browser_close_operation_id="finalize-original-browser",
        restore_operation_id="finalize-native-restore",
        resume_operation_id="finalize-native-resume",
        qualification_operation_id="finalize-reset-facts",
        reset_operation_id="finalize-safe-reset",
    )
    authority, unstarted, resume = (
        UnitFinalizationAuthority(p),
        UnitUnstartedAuthority(case),
        UnitResumeAuthority(p),
    )
    f = map_task_finalization(
        p.plan,
        d,
        put(p.original.resource.evidence, d),
        p.reset,
        p.preparation,
        lambda: browser,
        browser.journal,
        lambda: case.capture.state.closure_ref,
        authority,
        unstarted,
        resume,
        p.original.resource.evidence,
        p.original.resource.controls,
    )
    authority.finalizer = resume.finalizer = f
    return FinalizationPortCase(case, f, authority, unstarted, resume)
