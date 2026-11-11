"""Count a reading with the original resident native tokenizer, without inference.

The private count-only envelope is saved with real native command/reply facts.
It is explicitly rejected by the generation gate. The eventual actual Actor
request still needs its own complete-request count and independent send review.
"""

import hashlib
from lab_generate_skill.domain.actor_prompt import ActorPrompt, ActorMessage
from lab_generate_skill.domain.actor_observation_view import ActorObservationView
from lab_generate_skill.domain.actor_proposal_feedback import (
    ActorInvalidProposalProgress,
)
from lab_generate_skill.domain.observation_read_geometry import (
    reading_progress_fingerprint,
)
from lab_generate_skill.domain.context_budget import (
    ContextBudgetProfile,
    CountedContextInput,
)
from lab_generate_skill.domain.context_projection import ContextProjectionPolicy
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.observation_read import ObservationReadPayload
from lab_generate_skill.domain.observation_read_policy import ObservationReadPolicy
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.context_projection import (
    ContextTokenCounter,
    ContextTokenInputMeasure,
    ContextTokenReturnMeasure,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl


class ActorObservationBodyCounts:
    def __init__(
        self,
        counter: ContextTokenCounter,
        evidence: EvidenceStore,
        profile: ContextBudgetProfile,
        context_policy: ContextProjectionPolicy,
        read_policy: ObservationReadPolicy,
    ) -> None:
        self._counter, self._evidence = counter, evidence
        self._profile = ContextBudgetProfile.model_validate(profile)
        self._context_policy = ContextProjectionPolicy.model_validate(context_policy)
        self._read_policy = ObservationReadPolicy.model_validate(read_policy)
        if (
            self._profile.role != "actor"
            or self._profile.precision != "exact"
            or self._context_policy.role != "actor"
        ):
            raise ValueError("Original exact Actor profile and context policy required")

    def measure_body(
        self,
        payload: ObservationReadPayload,
        body: str,
        operation: OperationContext,
        *,
        control: OperationControl,
        retention_control: OperationControl | None = None,
    ) -> CountedContextInput:
        payload = ObservationReadPayload.model_validate(payload)
        operation = OperationContext.model_validate(operation)
        scope = payload.request.snapshot.scope
        if payload.request.snapshot.policy_sha256 != self._read_policy.digest or (
            operation.run_id,
            operation.owner_id,
            operation.attempt_id,
            operation.mode,
        ) != (scope.owner.run_id, scope.owner.owner_id, scope.attempt_id, "execute"):
            raise OwnershipConflict(
                "Reading count changed original snapshot, policy or operation"
            )
        new = self._read_policy.schema_version == "observation-read-policy/2"
        extra = {}
        if new:
            if payload.overview is None:
                raise OwnershipConflict(
                    "Policy2 count probe requires actual public tab overview"
                )
            extra = dict(
                schema_version="actor-observation-view/3",
                tab_count=len(payload.overview.tabs),
                invalid_proposals=ActorInvalidProposalProgress(),
                progress_fingerprint=reading_progress_fingerprint(payload),
            )
        view = ActorObservationView.model_validate(
            dict(
                snapshot=payload.request.snapshot,
                policy=self._read_policy,
                mode="local",
                source_spans=payload.covered_ranges,
                body_start=0,
                body_end=len(body),
                body_sha256=hashlib.sha256(body.encode()).hexdigest(),
                body_token_limit=self._read_policy.body_max_tokens,
                tools=("list_regions", "read_region", "search_regions"),
                read_result_ref=None,
                reads_used=0,
                no_progress=0,
                omissions=("count_probe_only",),
                **extra,
            )
        )
        prompt = ActorPrompt(
            prompt_version=(
                "browsergym-adaptive-count-probe-v2"
                if new
                else "browsergym-adaptive-count-probe-v1"
            ),
            observation_view=view,
            messages=(
                ActorMessage(
                    role="system",
                    content="Internal tokenizer probe only. Never dispatch for inference or treat as delivered Actor input.",
                ),
                ActorMessage(role="user", content=body),
            ),
        )
        control.checkpoint()
        reference = self._evidence.put(
            prompt.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="actor-model-input/1",
                visibility="private",
                producer="actor-reading-count-probe-v1",
            ),
            control,
        )
        counter = (
            self._counter.with_inputs(self._evidence)
            if isinstance(self._counter, ContextTokenInputMeasure)
            else self._counter
        )
        if retention_control is None:
            counted = counter.measure(
                reference, self._profile, self._context_policy, control=control
            )
        else:
            if not isinstance(counter, ContextTokenReturnMeasure):
                raise OwnershipConflict(
                    "Actual readonly counter lacks original reply-retention control"
                )
            counted = counter.measure_with_return(
                reference,
                self._profile,
                self._context_policy,
                control=control,
                retention_control=retention_control,
            )
        if counted.measurement.observation_body_sha256 != view.body_sha256:
            raise EvidenceIntegrityError(
                "Native reading probe counted a different exact body"
            )
        return counted
