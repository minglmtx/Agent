"""Original browser close, native restore/resume and complete measured Reset."""

import json
from lab_generate_skill.domain.source_recovery_budget import (
    SourceRecoveryBudgets,
    recovery_seconds,
)
from lab_generate_skill.adapters.sites.recorded_resume import RecordedSiteResume
from lab_generate_skill.adapters.sites.source_qualification_resume import (
    SourceQualificationResumeAuthority,
    PendingQualificationResume,
)
from lab_generate_skill.adapters.sites.source_qualification_state import (
    QualificationStateSelections,
)
from lab_generate_skill.adapters.storage.state_qualifications import (
    EvidenceStateQualifications,
)
from lab_generate_skill.domain.errors import OwnershipConflict, DispatchAlreadyCommitted
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.domain.reset import assemble_reset
from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.domain.state_qualification import ResetSelection
from .source_qualification_records import SourceQualificationRecords
from typing import Protocol
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_resume import SiteResumeResult
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl


class SourceRecoveryChecks(Protocol):
    def restore(
        self,
        request: SiteTaskRequest,
        result: SiteTaskResult,
        snapshot_ref: EvidenceRef,
        snapshot: bytes,
        control: OperationControl,
    ) -> None: ...
    def resume(
        self,
        request: SiteResumeRequest,
        result: SiteResumeResult,
        restored: SiteTaskResult,
        control: OperationControl,
    ) -> None: ...


def close_source_browser(
    records: SourceQualificationRecords, primary: BaseException | None = None
) -> None:
    p = records.progress
    b = p.browser
    if b is None or b.phase == "new":
        return
    if b.phase == "closed":
        if p.browser_closure_ref is None:
            raise OwnershipConflict(
                "Source browser closed without retained closure reference"
            )
        return
    op = b.operation.cleanup(
        records.prefix + ".browser-close",
        now=records.clock.utcnow(),
        seconds=recovery_seconds(
            records.recovery_budgets, "browser_close_seconds", 1800
        ),
    )
    record = b.close(op, records.controls.bind(op), primary=primary)
    ending = json.loads(
        records.reads.read(record.events[-1].evidence[0], records.controls.bind(op))
    )
    closure = ClosureReceipt.model_validate_json(
        json.dumps(ending["details"]["closure"])
    )
    if closure.token != b.spec.token or closure.status != "closed":
        raise OwnershipConflict(
            "Source browser ending did not confirm original full closure"
        )
    p.browser_closure_ref = records.put(closure, op)


def restore_source(
    records: SourceQualificationRecords,
    qualifications: EvidenceStateQualifications,
    checks: SourceRecoveryChecks,
) -> None:
    if not isinstance(records, SourceQualificationRecords) or any(
        not callable(getattr(checks, name, None)) for name in ("restore", "resume")
    ):
        raise TypeError(
            "Original source records and explicit recovery lineage checks required"
        )
    p = records.progress
    if p.restore_attempted:
        raise DispatchAlreadyCommitted("Original source restore was already attempted")
    if (
        p.prepare_request is None
        or p.prepare_result is None
        or p.snapshot_ref is None
        or p.browser_closure_ref is None
        or p.selections is None
        or p.reset_plan_ref is None
    ):
        raise OwnershipConflict(
            "Source restore requires original preparation/snapshot/browser closure"
        )
    p.restore_attempted = True
    p.phase = "restoring"
    op = p.prepare_request.operation.cleanup(
        records.prefix + ".restore",
        now=records.clock.utcnow(),
        seconds=recovery_seconds(records.recovery_budgets, "restore_seconds", 1200),
    )
    request, result, request_ref, result_ref = records.request("restore", op)
    checks.restore(
        request,
        result,
        p.snapshot_ref,
        records.reads.read(p.snapshot_ref, records.controls.bind(op)),
        records.controls.bind(op),
    )
    pending_restore = p.pending_native
    if pending_restore is None:
        raise OwnershipConflict("Source restore lost its original persisted intent")
    resume_op = op.cleanup(
        records.prefix + ".resume",
        now=records.clock.utcnow(),
        seconds=recovery_seconds(records.recovery_budgets, "resume_seconds", 600),
    ).model_copy(update={"recovery_ref": records.native.spec.token.recovery_ref})
    resume = SiteResumeRequest(
        restore_request=request, restore_result_ref=result_ref, operation=resume_op
    )
    p.pending_resume = PendingQualificationResume(
        resume, pending_restore, result, result_ref
    )
    recorder = RecordedSiteResume(
        records.site.resume,
        records.owner.evidence,
        SourceQualificationResumeAuthority(records.native, lambda: p.pending_resume),
    )
    resumed_ref = recorder.resume(resume, control=records.controls.bind(resume_op))
    if recorder.result is None or recorder.intent_ref is None:
        raise OwnershipConflict(
            "Source frontend resume lacks original acknowledged result/intent"
        )
    checks.resume(resume, recorder.result, result, records.controls.bind(resume_op))
    p.references.extend((recorder.intent_ref, resumed_ref))
    selection = ResetSelection(
        environment_selection_ref=p.selections.environment_ref,
        plan_ref=p.reset_plan_ref,
        restore_request_ref=request_ref,
        restore_result_ref=result_ref,
        resume_request_ref=records.put(resume, resume_op),
        resume_result_ref=resumed_ref,
        resume_intent_ref=recorder.intent_ref,
        closure_refs=(p.browser_closure_ref,),
    )
    selection_ref = records.put(selection, resume_op)
    p.selections = QualificationStateSelections(
        p.selections.environment,
        p.selections.environment_ref,
        selection,
        selection_ref,
        pending_restore,
    )
    qualification_op = p.prepare_request.operation.cleanup(
        records.prefix + ".reset-facts",
        now=records.clock.utcnow(),
        seconds=recovery_seconds(records.recovery_budgets, "reset_facts_seconds", 1800),
    ).model_copy(update={"recovery_ref": records.native.spec.token.recovery_ref})
    p.reset_inputs = qualifications.publish_reset_facts(selection_ref, qualification_op)
    p.reset = assemble_reset(p.reset_inputs, qualification_op)
    if p.reset.status != "safe":
        raise OwnershipConflict("Actual complete source Reset is not safe")
    p.phase = "reset-safe"
