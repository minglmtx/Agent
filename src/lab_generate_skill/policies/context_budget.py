"""Finite deterministic choice; soft guides selection, hard always limits input."""

from typing import Literal
from lab_generate_skill.domain.context_projection import (
    ContextSelection,
    ContextDecision,
    ContextCandidateAssessment,
)


def select_candidate(request: ContextSelection) -> ContextDecision:
    request = ContextSelection.model_validate(request)
    if request.schema_version == "context-selection/2":
        from .actor_observation_selection import select_adaptive_observation

        return select_adaptive_observation(request)
    profile, policy = request.profile, request.policy
    assessments = []
    for candidate in request.candidates:
        statuses = {check.status for check in candidate.checks}
        integrity: Literal["pass", "fail", "unknown"] = (
            "fail"
            if "fail" in statuses
            else "unknown" if "unknown" in statuses else "pass"
        )
        tokens = candidate.measurement.upper_bound_tokens
        assessments.append(
            ContextCandidateAssessment(
                candidate_id=candidate.candidate_id,
                input_ref=candidate.measurement.input_ref,
                input_tokens=candidate.measurement.input_tokens,
                budget_tokens=tokens,
                integrity=integrity,
                within_soft=tokens <= profile.soft_target,
                within_hard=tokens <= profile.hard_limit
                and tokens + profile.output_reserve + profile.uncounted_overhead
                <= profile.context_window,
            )
        )
    base = assessments[0]
    chosen: ContextCandidateAssessment | None = None
    reason = "input_budget_exceeded"
    if base.integrity != "pass":
        reason = "integrity_rejected"
    elif policy.forced_kind is not None:
        index = policy.candidate_order.index(policy.forced_kind)
        target = assessments[index]
        if target.integrity != "pass":
            reason = "integrity_rejected"
        elif target.within_hard:
            chosen, reason = target, "explicit_format"
    elif base.within_soft and base.within_hard:
        chosen, reason = base, "below_soft_identity"
    else:
        smaller = [
            a
            for a in assessments[1:]
            if a.integrity == "pass"
            and a.within_hard
            and a.budget_tokens < base.budget_tokens
        ]
        if smaller:
            chosen, reason = (
                min(smaller, key=lambda a: a.budget_tokens),
                "shorter_verified_candidate",
            )
        elif base.within_hard and policy.allow_identity_fallback:
            chosen, reason = base, "identity_fallback"
        elif base.within_hard:
            reason = "no_permitted_candidate"
    return ContextDecision.model_validate(
        dict(
            source=request.candidates[0].source,
            profile_sha256=profile.digest,
            policy_sha256=policy.digest,
            selection_sha256=request.digest,
            accepted=chosen is not None,
            reason_code=reason,
            selected_candidate_id=None if chosen is None else chosen.candidate_id,
            selected_input_ref=None if chosen is None else chosen.input_ref,
            assessments=tuple(assessments),
        )
    )
