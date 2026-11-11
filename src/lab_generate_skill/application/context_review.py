"""Read-only preparation audit; actual send/return review remains original caller.

Rebuild the same frozen formats, independently recheck protected relations and
original count evidence, and compare the recorded decision. Never recount,
change strategy or claim an actual send from a comparison of small references.
"""

import hashlib
from dataclasses import dataclass
from lab_generate_skill.domain.context_preparation import (
    ContextPreparationRequest,
    ContextPreparationReceipt,
    PreparedContextRef,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.context_projection import (
    ContextPreparationAuthority,
    ContextInputProjector,
    ContextProtectionVerifier,
    ContextCountEvidenceVerifier,
)
from lab_generate_skill.policies.context_budget import select_candidate
from .context_evidence import read_bytes, read_document
from .context_preparation import checked_drafts


@dataclass(frozen=True)
class ContextReviewDeps:
    evidence: EvidenceReader
    authority: ContextPreparationAuthority
    projector: ContextInputProjector
    protection: ContextProtectionVerifier
    counts: ContextCountEvidenceVerifier


def review_context(
    request: ContextPreparationRequest,
    prepared: PreparedContextRef,
    deps: ContextReviewDeps,
    *,
    expected_input_ref: EvidenceRef | None,
    control: OperationControl,
) -> ContextPreparationReceipt:
    request = ContextPreparationRequest.model_validate(request)
    prepared = PreparedContextRef.model_validate(prepared)
    control.checkpoint()
    deps.authority.verify_recorded(request, prepared.reference, control=control)
    if (
        prepared.request_sha256
        != hashlib.sha256(request.model_dump_json().encode()).hexdigest()
    ):
        raise EvidenceIntegrityError("Preparation changed original logical request")
    receipt = read_document(
        deps.evidence, prepared.reference, ContextPreparationReceipt, control
    )
    if (
        receipt.request != request
        or receipt.outcome != prepared.outcome
        or expected_input_ref != prepared.selected_input_ref
    ):
        raise EvidenceIntegrityError(
            "Saved preparation changed original request/outcome/input binding"
        )
    original = read_bytes(
        deps.evidence,
        request.source.original_ref,
        (8 if request.source.role == "actor" else 64) * 1024**2,
        control,
    )
    drafts = checked_drafts(request, original, deps.projector)
    if request.policy.schema_version in (
        "context-projection-policy/2",
        "context-projection-policy/3",
    ):
        if len(receipt.drafts) > len(drafts):
            raise EvidenceIntegrityError(
                "Recorded adaptive evaluation exceeded frozen candidate order"
            )
        if (
            len(receipt.drafts) < len(drafts)
            and receipt.outcome != "integrity_rejected"
        ):
            complete_fits = (
                len(receipt.counts) == 1
                and drafts[0].kind == "compact_full_ax"
                and receipt.counts[0].measurement.upper_bound_tokens
                <= min(request.profile.soft_target, request.profile.hard_limit)
            )
            navigation_fits = (
                request.policy.schema_version == "context-projection-policy/3"
                and len(receipt.counts) == len(receipt.drafts)
                and receipt.drafts[-1].kind == "local_ax"
                and receipt.selection is not None
                and select_candidate(receipt.selection).accepted
                and select_candidate(receipt.selection).selected_input_ref
                == receipt.drafts[-1].input_ref
            )
            if not (complete_fits or navigation_fits):
                raise EvidenceIntegrityError(
                    "Recorded adaptive preparation omitted the required local evaluation"
                )
        drafts = drafts[: len(receipt.drafts)]
    for draft, record in zip(drafts, receipt.drafts, strict=True):
        if (draft.candidate_id, draft.kind) != (
            record.candidate_id,
            record.kind,
        ) or read_bytes(
            deps.evidence,
            record.input_ref,
            (8 if request.source.role == "actor" else 64) * 1024**2,
            control,
        ) != draft.input_bytes:
            raise EvidenceIntegrityError(
                "Recorded complete input differs from frozen source/format"
            )
        checks = deps.protection.verify(request.source, original, draft, request.policy)
        if (
            read_bytes(deps.evidence, record.audit_ref, 64 * 1024**2, control)
            != draft.audit.model_dump_json().encode()
        ):
            raise EvidenceIntegrityError("Recorded full transformation audit changed")
        if checks != record.checks:
            raise EvidenceIntegrityError(
                "Independent protection differs from recorded facts"
            )
    for counted in receipt.counts:
        if (
            deps.counts.verify(
                counted, request.profile, request.policy, control=control
            )
            != counted.measurement
        ):
            raise EvidenceIntegrityError(
                "Independent count verification returned foreign facts"
            )
    if receipt.selection is not None:
        decision = select_candidate(receipt.selection)
        if (
            decision != receipt.decision
            or decision.selected_input_ref != prepared.selected_input_ref
        ):
            raise EvidenceIntegrityError(
                "Recorded selection changed frozen policy or complete inputs"
            )
    control.checkpoint()
    return receipt
