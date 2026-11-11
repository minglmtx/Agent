"""Allowed role input preparation over existing CAS and controlled ports.

Does not launch resources, grant source/fee rights, write a model intent, send,
retry or infer. Original pending/unknown checks are mandatory authority work.
"""

import hashlib
from dataclasses import dataclass
from lab_generate_skill.domain.adaptive_candidates import (
    adaptive_candidate_ids,
    adaptive_candidate_kind,
)
from lab_generate_skill.domain.context_preparation import (
    ContextPreparationRequest,
    ContextPreparationReceipt,
    ContextInputDraft,
    ContextDraftRecord,
    PreparedContextRef,
)
from lab_generate_skill.domain.context_projection import (
    MeasuredContextCandidate,
    ContextSelection,
)
from lab_generate_skill.domain.context_projection import ContextProtectionCheck
from lab_generate_skill.domain.context_budget import CountedContextInput
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn
from lab_generate_skill.domain.context_projection import ActorContextSource
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.context_projection import (
    ContextPreparationAuthority,
    ContextInputProjector,
    ContextProtectionVerifier,
    ContextTokenCounter,
)
from lab_generate_skill.policies.context_budget import select_candidate
from .context_evidence import read_bytes, publish_bytes


@dataclass(frozen=True)
class ContextPreparationDeps:
    evidence: EvidenceStore
    authority: ContextPreparationAuthority
    projector: ContextInputProjector
    protection: ContextProtectionVerifier
    counter: ContextTokenCounter


class ContextPreparationUnconfirmed(RuntimeError):
    def __init__(
        self,
        request: ContextPreparationRequest,
        phase: str,
        primary: BaseException,
        retained: tuple[EvidenceRef, ...],
    ) -> None:
        self.request, self.phase, self.primary, self.retained = (
            request,
            phase,
            primary,
            retained,
        )
        super().__init__(
            "Context preparation stopped; preserve original facts without automatic retry"
        )


def checked_drafts(
    request: ContextPreparationRequest,
    original: bytes,
    projector: ContextInputProjector,
) -> tuple[ContextInputDraft, ...]:
    returned = projector.project(request.source, original, request.policy)
    expected = request.policy.candidate_order
    observed = None
    if request.policy.schema_version in (
        "context-projection-policy/2",
        "context-projection-policy/3",
    ):
        if not isinstance(request.source, ActorContextSource):
            raise EvidenceIntegrityError("Adaptive Actor source required")
        public = ActorPublicTurn.model_validate_json(original)
        observed = public.observation_source
        if (
            observed is None
            or request.source.active_read_ref != observed.read_result_ref
        ):
            raise EvidenceIntegrityError(
                "Adaptive source changed original active read lineage"
            )
        expected = (
            ("local_ax",)
            if request.source.active_read_ref is not None
            else (
                request.policy.candidate_order
                if observed.eligibility == "local_supported"
                else ("compact_full_ax",)
            )
        )
    if request.policy.schema_version == "context-projection-policy/3":
        if not isinstance(request.source, ActorContextSource) or observed is None:
            raise EvidenceIntegrityError("Adaptive Actor public source required")
        ids = adaptive_candidate_ids(
            request.policy.schema_version,
            active_read=request.source.active_read_ref is not None,
            local_supported=observed.eligibility == "local_supported",
        )
        expected = tuple(adaptive_candidate_kind(identity) for identity in ids)
        if (
            type(returned) is not tuple
            or tuple(d.candidate_id for d in returned) != ids
        ):
            raise EvidenceIntegrityError(
                "Adaptive navigation candidate identities changed"
            )
    if type(returned) is not tuple or len(returned) != len(expected):
        raise EvidenceIntegrityError(
            "Projector omitted declared candidates or changed container"
        )
    drafts = tuple(ContextInputDraft.model_validate(d) for d in returned)
    if (
        tuple(d.kind for d in drafts) != expected
        or len({d.candidate_id for d in drafts}) != len(drafts)
        or any(
            d.source != request.source or d.policy_sha256 != request.policy.digest
            for d in drafts
        )
    ):
        raise EvidenceIntegrityError(
            "Projector changed original candidate/source/policy bindings"
        )
    return drafts


def prepare_context(
    request: ContextPreparationRequest,
    deps: ContextPreparationDeps,
    *,
    control: OperationControl,
) -> PreparedContextRef:
    request = ContextPreparationRequest.model_validate(request)
    retained: list[EvidenceRef] = []
    phase = "authority"
    try:
        control.checkpoint()
        deps.authority.verify_prepare(request, control=control)
        phase = "source"
        original = read_bytes(
            deps.evidence,
            request.source.original_ref,
            (8 if request.source.role == "actor" else 64) * 1024**2,
            control,
        )
        if request.policy.schema_version in (
            "context-projection-policy/2",
            "context-projection-policy/3",
        ):
            from .adaptive_context_preparation import prepare_adaptive_context

            phase = "adaptive_preparation"
            return prepare_adaptive_context(
                request, deps, original, retained, control=control
            )
        phase = "projection"
        drafts = checked_drafts(request, original, deps.projector)
        phase = "protection"
        checks_list: list[tuple[ContextProtectionCheck, ...]] = []
        for draft in drafts:
            result = deps.protection.verify(
                request.source, original, draft, request.policy
            )
            if type(result) is not tuple:
                raise EvidenceIntegrityError(
                    "Protection verifier changed its exact container"
                )
            checks_list.append(
                tuple(ContextProtectionCheck.model_validate(c) for c in result)
            )
        checks = tuple(checks_list)
        if any(
            {c.name for c in result} != set(request.policy.protected_rules)
            or len({c.name for c in result}) != len(result)
            for result in checks
        ):
            raise EvidenceIntegrityError(
                "Independent protection omitted or repeated a rule"
            )
        phase = "save_inputs"
        records = tuple(
            ContextDraftRecord(
                candidate_id=draft.candidate_id,
                kind=draft.kind,
                input_ref=publish_bytes(
                    deps.evidence,
                    draft.input_bytes,
                    request.source.role + "-model-input/1",
                    retained,
                    control,
                ),
                audit_ref=publish_bytes(
                    deps.evidence,
                    draft.audit.model_dump_json().encode(),
                    draft.audit.schema_version,
                    retained,
                    control,
                ),
                checks=result,
            )
            for draft, result in zip(drafts, checks, strict=True)
        )
        counts: tuple[CountedContextInput, ...] = ()
        selection = None
        decision = None
        outcome = "integrity_rejected"
        if all(c.status == "pass" for result in checks for c in result):
            phase = "count"
            counted_inputs: list[CountedContextInput] = []
            for record in records:
                counted = CountedContextInput.model_validate(
                    deps.counter.measure(
                        record.input_ref,
                        request.profile,
                        request.policy,
                        control=control,
                    )
                )
                retained.append(counted.evidence_ref)
                measured = counted.measurement
                if (
                    measured.input_ref != record.input_ref
                    or measured.profile_sha256 != request.profile.digest
                    or measured.policy_sha256 != request.policy.digest
                    or measured.role != request.source.role
                    or measured.precision != request.profile.precision
                ):
                    raise EvidenceIntegrityError(
                        "Count returned foreign source/profile/policy facts"
                    )
                counted_inputs.append(counted)
            counts = tuple(counted_inputs)
            phase = "selection"
            selection = ContextSelection(
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
        phase = "save_receipt"
        receipt = ContextPreparationReceipt.model_validate(
            dict(
                request=request,
                outcome=outcome,
                drafts=records,
                counts=counts,
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
            request_sha256=hashlib.sha256(
                request.model_dump_json().encode()
            ).hexdigest(),
            reference=reference,
            outcome=receipt.outcome,
            selected_input_ref=(
                decision.selected_input_ref if decision is not None else None
            ),
        )
    except BaseException as error:
        raise ContextPreparationUnconfirmed(
            request, phase, error, tuple(retained)
        ) from error
