"""Two finite actual Actor modes; complete-request and local-body limits differ."""

from typing import Literal
from lab_generate_skill.domain.actor_projection import AdaptiveObservationProjection
from lab_generate_skill.domain.context_projection import (
    ContextSelection,
    ContextDecision,
    ContextCandidateAssessment,
)


def select_adaptive_observation(request: ContextSelection) -> ContextDecision:
    request = ContextSelection.model_validate(request)
    projection = request.policy.actor_projection
    if request.schema_version != "context-selection/2" or not isinstance(
        projection, AdaptiveObservationProjection
    ):
        raise ValueError("Explicit original adaptive Actor selection required")
    profile = request.profile
    assessments = []
    for candidate in request.candidates:
        states = {check.status for check in candidate.checks}
        integrity: Literal["pass", "fail", "unknown"] = (
            "fail" if "fail" in states else "unknown" if "unknown" in states else "pass"
        )
        measurement = candidate.measurement
        tokens = measurement.upper_bound_tokens
        body_ok = True
        if candidate.kind == "local_ax":
            if (
                measurement.observation_tokens is None
                or measurement.observation_body_sha256 is None
            ):
                integrity = "unknown"
                body_ok = False
            else:
                body_ok = (
                    measurement.observation_tokens
                    <= projection.read_policy.body_max_tokens
                )
        assessments.append(
            ContextCandidateAssessment(
                candidate_id=candidate.candidate_id,
                input_ref=measurement.input_ref,
                input_tokens=measurement.input_tokens,
                budget_tokens=tokens,
                integrity=integrity,
                within_soft=body_ok and tokens <= profile.soft_target,
                within_hard=body_ok
                and tokens <= profile.hard_limit
                and tokens + profile.output_reserve + profile.uncounted_overhead
                <= profile.context_window,
            )
        )
    first = assessments[0]
    selected: ContextCandidateAssessment | None = None
    reason = "input_budget_exceeded"
    kinds = tuple(candidate.kind for candidate in request.candidates)
    if any(assessment.integrity != "pass" for assessment in assessments):
        reason = "integrity_rejected"
    elif kinds == ("local_ax",):
        if first.within_hard:
            selected, reason = first, "adaptive_local"
    elif first.within_soft and first.within_hard:
        if len(assessments) != 1:
            raise ValueError(
                "Small complete input already qualifies; unnecessary local measurement is not the actual branch"
            )
        selected, reason = first, "adaptive_compact_full"
    else:
        selected = next((item for item in assessments[1:] if item.within_hard), None)
        if selected is not None:
            reason = "adaptive_local"
        elif first.within_hard and (
            request.policy.allow_identity_fallback
            or (
                request.policy.schema_version == "context-projection-policy/3"
                and kinds == ("compact_full_ax",)
            )
        ):
            # A full-required source has no local candidate. Its complete input
            # may cross the soft preference while still satisfying the hard gate;
            # recorded-source review independently proves that exact capability.
            selected, reason = first, "adaptive_complete_required"
        elif first.within_hard:
            reason = "no_permitted_candidate"
    return ContextDecision.model_validate(
        dict(
            schema_version="context-budget-decision/2",
            source=request.candidates[0].source,
            profile_sha256=profile.digest,
            policy_sha256=request.policy.digest,
            selection_sha256=request.digest,
            accepted=selected is not None,
            reason_code=reason,
            selected_candidate_id=None if selected is None else selected.candidate_id,
            selected_input_ref=None if selected is None else selected.input_ref,
            assessments=tuple(assessments),
        )
    )
