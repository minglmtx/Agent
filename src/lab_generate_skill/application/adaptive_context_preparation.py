"""Evaluate only the necessary prefix of the two declared Actor input modes."""

import hashlib
from typing import TYPE_CHECKING
from lab_generate_skill.domain.context_preparation import (
    ContextPreparationRequest,
    ContextPreparationReceipt,
    ContextDraftRecord,
    PreparedContextRef,
)
from lab_generate_skill.domain.context_budget import CountedContextInput
from lab_generate_skill.domain.context_projection import (
    ContextProtectionCheck,
    ContextSelection,
    MeasuredContextCandidate,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.actor_projection import AdaptiveObservationProjection
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.context_budget import select_candidate
from .context_evidence import publish_bytes

if TYPE_CHECKING:
    from .context_preparation import ContextPreparationDeps


def prepare_adaptive_context(
    request: ContextPreparationRequest,
    deps: "ContextPreparationDeps",
    original: bytes,
    retained: list[EvidenceRef],
    *,
    control: OperationControl,
) -> PreparedContextRef:
    from .context_preparation import checked_drafts

    projection = request.policy.actor_projection
    if not isinstance(projection, AdaptiveObservationProjection):
        raise EvidenceIntegrityError("Explicit adaptive projection required")
    drafts = checked_drafts(request, original, deps.projector)
    records = []
    counts: list[CountedContextInput] = []
    same_input_counts: dict[EvidenceRef, CountedContextInput] = {}
    same_input_refs: dict[bytes, EvidenceRef] = {}
    outcome = "integrity_rejected"
    selection = None
    decision = None
    for draft in drafts:
        control.checkpoint()
        checked = deps.protection.verify(
            request.source, original, draft, request.policy
        )
        if type(checked) is not tuple:
            raise EvidenceIntegrityError(
                "Adaptive protection returned a foreign container"
            )
        checks = tuple(
            ContextProtectionCheck.model_validate(check) for check in checked
        )
        if len({check.name for check in checks}) != len(checks) or {
            check.name for check in checks
        } != set(request.policy.protected_rules):
            raise EvidenceIntegrityError(
                "Every frozen adaptive protection relation must be checked"
            )
        input_ref = same_input_refs.get(draft.input_bytes)
        if input_ref is None:
            input_ref = publish_bytes(
                deps.evidence,
                draft.input_bytes,
                "actor-model-input/1",
                retained,
                control,
            )
            same_input_refs[draft.input_bytes] = input_ref
        record = ContextDraftRecord(
            candidate_id=draft.candidate_id,
            kind=draft.kind,
            input_ref=input_ref,
            audit_ref=publish_bytes(
                deps.evidence,
                draft.audit.model_dump_json().encode(),
                draft.audit.schema_version,
                retained,
                control,
            ),
            checks=checks,
        )
        records.append(record)
        if not all(check.status == "pass" for check in checks):
            break
        counted = same_input_counts.get(record.input_ref)
        if counted is None:
            counted = CountedContextInput.model_validate(
                deps.counter.measure(
                    record.input_ref, request.profile, request.policy, control=control
                )
            )
            same_input_counts[record.input_ref] = counted
        measured = counted.measurement
        if (
            measured.input_ref,
            measured.profile_sha256,
            measured.policy_sha256,
            measured.role,
            measured.precision,
        ) != (
            record.input_ref,
            request.profile.digest,
            request.policy.digest,
            "actor",
            request.profile.precision,
        ):
            raise EvidenceIntegrityError(
                "Adaptive native measurement changed original input/profile/policy"
            )
        retained.append(counted.evidence_ref)
        counts.append(counted)
        # The selected body/full input will be checked again by the original
        # final send authority. This is finite preparation, never a send permit.
        if (
            draft.kind == "compact_full_ax"
            and measured.upper_bound_tokens <= request.profile.soft_target
            and measured.upper_bound_tokens <= request.profile.hard_limit
        ):
            break
        if (
            request.policy.schema_version == "context-projection-policy/3"
            and draft.kind == "local_ax"
            and measured.observation_tokens is not None
            and measured.observation_tokens <= projection.read_policy.body_max_tokens
            and measured.upper_bound_tokens <= request.profile.hard_limit
            and measured.upper_bound_tokens
            + request.profile.output_reserve
            + request.profile.uncounted_overhead
            <= request.profile.context_window
        ):
            break
    if len(counts) == len(records):
        selection = ContextSelection(
            schema_version="context-selection/2",
            profile=request.profile,
            policy=request.policy,
            candidates=tuple(
                MeasuredContextCandidate(
                    candidate_id=record.candidate_id,
                    kind=record.kind,
                    source=request.source,
                    policy_sha256=request.policy.digest,
                    measurement=counted.measurement,
                    checks=record.checks,
                )
                for record, counted in zip(records, counts, strict=True)
            ),
        )
        decision = select_candidate(selection)
        outcome = "prepared" if decision.accepted else "budget_rejected"
    receipt = ContextPreparationReceipt.model_validate(
        dict(
            request=request,
            outcome=outcome,
            drafts=tuple(records),
            counts=tuple(counts),
            selection=selection,
            decision=decision,
        )
    )
    reference = publish_bytes(
        deps.evidence,
        receipt.model_dump_json().encode(),
        receipt.schema_version,
        retained,
        control,
    )
    return PreparedContextRef(
        request_sha256=hashlib.sha256(request.model_dump_json().encode()).hexdigest(),
        reference=reference,
        outcome=receipt.outcome,
        selected_input_ref=None if decision is None else decision.selected_input_ref,
    )
