"""Original browser closure or independently authorized original non-start.

No launch, takeover, replacement or new ResourceJournal history. A missing
handle/registration alone never establishes physical non-start or closure.
"""

from collections.abc import Callable
import json
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import ClosureReceipt, OperationContext
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_finalization import (
    TaskFinalizationPlan,
    UnstartedTaskBrowser,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import ResourceJournal, OperationControl
from lab_generate_skill.ports.task_finalization import UnstartedTaskBrowserAuthority
from lab_generate_skill.adapters.storage.capture_evidence import CaptureEvidence
from lab_generate_skill.policies.evidence_bytes import (
    require_complete_bytes,
    require_complete_read_bound,
)
from .retained_resource import RetainedBrowserResource


class OriginalTaskBrowserFinalizer:
    def __init__(
        self,
        browser: Callable[[], RetainedBrowserResource | None],
        journal: ResourceJournal,
        unstarted: UnstartedTaskBrowserAuthority,
        evidence: EvidenceStore,
        known_closure: Callable[[], EvidenceRef | None],
    ) -> None:
        if any(
            x is None for x in (browser, journal, unstarted, evidence, known_closure)
        ):
            raise ValueError(
                "Original browser/journal/non-start authority/closure provider required"
            )
        self.browser, self.journal, self.unstarted = browser, journal, unstarted
        self.evidence, self.known_closure = evidence, known_closure
        self.writer = CaptureEvidence(evidence, "task-browser-finalization-v1")
        self.references: list[EvidenceRef] = []

    def _read(self, ref: EvidenceRef, control: OperationControl, limit: int) -> bytes:
        require_complete_read_bound(ref, limit)
        raw = self.evidence.read(ref, control=control)
        require_complete_bytes(ref, raw)
        control.checkpoint()
        return raw

    def close(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskFinalizationPlan,
        declaration_ref: EvidenceRef,
        reset: ResetPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> tuple[ClosureReceipt, EvidenceRef]:
        if (
            len(reset.attempt_allocations) != 1
            or reset.attempt_allocations[0].resource_kind != "browser"
        ):
            raise OwnershipConflict(
                "This consumer closes exactly its one declared attempt browser"
            )
        token = reset.attempt_allocations[0]
        browser = self.browser()
        if browser is not None and (
            browser.spec.token != token or browser.journal is not self.journal
        ):
            raise OwnershipConflict(
                "Finalization changed original browser owner/journal"
            )
        if browser is None or browser.phase == "new":
            read = operation.model_copy(
                update={
                    "operation_id": declaration.browser_close_operation_id,
                    "allocation_id": token.allocation_id,
                    "recovery_ref": token.recovery_ref,
                }
            )
            # Original read() intentionally requires an existing stable lock;
            # never treat its integrity errors as fresh/empty history. Existing
            # discovery is read-only and validates every retained namespace.
            registrations = self.journal.records(token.owner, read)
            if any(r.token.allocation_id == token.allocation_id for r in registrations):
                raise OwnershipConflict(
                    "Original browser registration exists; absence of handle is not non-start"
                )
            observed = UnstartedTaskBrowser(
                scope=reset.scope,
                token=token,
                operation=read,
                reset_plan_ref=plan.reset_plan_ref,
                preparation_declaration_ref=plan.declaration_ref,
                finalization_declaration_ref=declaration_ref,
                owner_phase="not_constructed" if browser is None else "new",
            )
            ref = self.writer.put(
                observed.model_dump_json().encode(), observed.schema_version, control
            )
            self.references.append(ref)
            closure = ClosureReceipt.model_validate(
                self.unstarted.close_unstarted(
                    plan, declaration, observed, ref, read, control
                )
            )
            closed_ref = self.writer.put(
                closure.model_dump_json().encode(), closure.schema_version, control
            )
            self.references.append(closed_ref)
            if (
                closure.token != token
                or closure.operation_id != read.operation_id
                or closure.status != "closed"
                or closure.primary_error is not None
            ):
                raise OwnershipConflict(
                    "Original physical non-start has not been independently confirmed"
                )
            return closure, closed_ref
        # The retained owner performs its original exit at most once. A prior
        # capture close/start failure can only reconcile its original ending.
        read = operation.model_copy(
            update={
                "operation_id": declaration.browser_close_operation_id,
                "parent_operation_id": browser.operation.operation_id,
                "allocation_id": token.allocation_id,
                "recovery_ref": token.recovery_ref,
            }
        )
        try:
            record = browser.close(read, control)
        except BaseException:
            if browser.closed is not None:
                self.references.extend(browser.closed.events[-1].evidence)
            raise
        ending_ref = record.events[-1].evidence[0]
        self.references.append(ending_ref)
        ending = json.loads(self._read(ending_ref, control, 64 * 1024**2))
        closure = ClosureReceipt.model_validate_json(
            json.dumps(ending["details"]["closure"])
        )
        known = self.known_closure()
        if known is not None:
            if (known.content_schema, known.visibility, known.media_type) != (
                "closure-receipt/1",
                "private",
                "application/json",
            ) or self._read(
                known, control, 2 * 1024**2
            ) != closure.model_dump_json().encode():
                raise OwnershipConflict(
                    "Known closure changed original complete browser ending"
                )
            ref = known
        else:
            ref = self.writer.put(
                closure.model_dump_json().encode(), closure.schema_version, control
            )
        self.references.append(ref)
        return closure, ref
