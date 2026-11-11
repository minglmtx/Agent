"""Original trace prefix + recorded selected input; never recount or choose anew."""

from copy import deepcopy
import hashlib
import threading
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_generation import ActorGeneration
from lab_generate_skill.domain.actor_context import ActorPreparedInput
from lab_generate_skill.domain.actor_prompt import ActorPrompt, ActorPublicTurn
from lab_generate_skill.domain.actor_response import ActorTextCompletion
from lab_generate_skill.domain.trace import TraceTurn
from lab_generate_skill.domain.observation_read import (
    ObservationReadPayload,
    ObservationReadRequest,
)
from lab_generate_skill.policies.observation_index import ObservationIndex
from .actor_read_review import review_actor_read
from lab_generate_skill.domain.context_preparation import (
    ContextPreparationRequest,
    ContextPreparationReceipt,
    PreparedContextRef,
)
from lab_generate_skill.domain.trace_events import GenerationIntent
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader, EvidenceStore
from lab_generate_skill.ports.observations import Observations, ObservationInputReads
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.actor_context import (
    ActorObservationSources,
    ActorRecordedProposalChecks,
)
from lab_generate_skill.ports.context_projection import (
    ContextInputProjector,
    ContextProtectionVerifier,
    ContextCountEvidenceVerifier,
    ContextCountInputReview,
)
from .actor_context_inputs import (
    actor_context_configuration,
    actor_public_fact,
    original_context_request,
)
from .context_evidence import read_document
from .context_review import ContextReviewDeps, review_context
from .actor_context_review_inputs import ActorContextReviewInputs
from .actor_context_preparation_inputs import ActorContextPreparationInputs
from .verified_evidence_inputs import verified_input_document


class _RecordedContextAuthority:
    def __init__(
        self, request: ContextPreparationRequest, reference: EvidenceRef
    ) -> None:
        self.request, self.reference = request, reference

    def verify_prepare(
        self, request: ContextPreparationRequest, *, control: OperationControl
    ) -> None:
        raise OwnershipConflict("Historical verification cannot prepare a model input")

    def verify_recorded(
        self,
        request: ContextPreparationRequest,
        reference: EvidenceRef,
        *,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if request != self.request or reference != self.reference:
            raise OwnershipConflict("Original context provenance changed")


class RecordedActorContextInputs:
    def __init__(
        self,
        evidence: EvidenceReader,
        observations: Observations,
        projector: ContextInputProjector,
        protection: ContextProtectionVerifier,
        counts: ContextCountEvidenceVerifier,
        *,
        retain_inputs: bool = False,
        request: ActorRunRequest | None = None,
        observation_sources: ActorObservationSources | None = None,
    ) -> None:
        self.evidence, self.observations = evidence, observations
        self.projector, self.protection, self.counts = projector, protection, counts
        self._retain_inputs = retain_inputs
        self.observation_sources = observation_sources
        self._request = ActorRunRequest.model_validate(request) if request else None
        if self._request is not None and not retain_inputs:
            raise ValueError("Bound generation inputs require explicit retention")
        self._thread = threading.get_ident()
        self._closed = False
        self._proposal_input: tuple[ActorPrompt, ActorPublicTurn] | None = None
        self._reading_indices: dict[str, ObservationIndex] = {}
        self._input_key: tuple[ActorRunRequest, GenerationIntent] | None = None
        self._inputs: ActorContextReviewInputs | None = None
        self._preparation_key: tuple[ActorRunRequest, OperationContext, str] | None = (
            None
        )
        self._prepared: ActorPreparedInput | None = None
        self._reviewed: (
            tuple[
                ActorRunRequest,
                TraceSnapshot,
                GenerationIntent,
                OperationContext,
                ActorPrompt,
            ]
            | None
        ) = None

    def clear_inputs(self) -> None:
        self._closed = True
        self._drop_inputs()
        self._reading_indices.clear()
        if self.observation_sources is not None:
            self.observation_sources.clear_inputs()

    def _drop_inputs(self) -> None:
        if self._inputs is not None:
            self._inputs.clear()
        self._proposal_input = None
        self._inputs, self._input_key = None, None
        self._preparation_key, self._prepared, self._reviewed = None, None, None

    def verify_proposal(
        self,
        prompt: ActorPrompt,
        reading: ObservationReadRequest,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if (
            self._closed
            or self._thread != threading.get_ident()
            or self._proposal_input is None
            or self._proposal_input[0] != prompt
            or not isinstance(self.observation_sources, ActorRecordedProposalChecks)
            or (operation.run_id, operation.owner_id, operation.attempt_id)
            != (
                reading.snapshot.scope.owner.run_id,
                reading.snapshot.scope.owner.owner_id,
                reading.snapshot.scope.attempt_id,
            )
        ):
            raise OwnershipConflict(
                "Recorded proposal requires its just-verified original input and scope"
            )
        self.observation_sources.check_recorded_proposal(
            self._proposal_input[1], prompt, reading, control=control
        )

    def verify_reading(
        self,
        request: ActorRunRequest,
        turn: TraceTurn,
        prompt: ActorPrompt,
        completion: ActorTextCompletion,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> ObservationReadPayload:
        if self._closed or self._thread != threading.get_ident():
            raise OwnershipConflict("Original read verifier lifetime or thread changed")
        request = ActorRunRequest.model_validate(request)
        configuration = actor_context_configuration(request, self.evidence, control)
        return review_actor_read(
            request,
            turn,
            prompt,
            completion,
            operation,
            configuration,
            self.evidence,
            self.observations,
            self.counts,
            self._reading_indices,
            control,
        )

    def preparation_inputs(
        self,
        request: ActorRunRequest,
        operation: OperationContext,
        request_id: str,
        original: EvidenceStore,
        control: OperationControl,
    ) -> EvidenceStore:
        control.checkpoint()
        request = ActorRunRequest.model_validate(request)
        operation = OperationContext.model_validate(operation)
        if (
            self._closed
            or self._thread != threading.get_ident()
            or not self._retain_inputs
            or request != self._request
            or original is not self.evidence
            or (
                operation.run_id,
                operation.owner_id,
                operation.attempt_id,
                operation.mode,
            )
            != (
                request.scope.owner.run_id,
                request.scope.owner.owner_id,
                request.scope.attempt_id,
                "execute",
            )
        ):
            raise OwnershipConflict(
                "Preparation inputs changed original run/lifetime/store"
            )
        self._drop_inputs()
        self._preparation_key = (request, operation, request_id)
        inputs = ActorContextPreparationInputs(original)
        self._inputs = inputs
        return inputs

    def prepared_inputs(
        self, prepared: ActorPreparedInput, control: OperationControl
    ) -> None:
        control.checkpoint()
        prepared = ActorPreparedInput.model_validate(prepared)
        if (
            self._closed
            or self._thread != threading.get_ident()
            or self._preparation_key is None
            or self._inputs is None
            or self._prepared is not None
        ):
            raise OwnershipConflict("Original pending preparation handoff required")
        for ref in (prepared.input_ref, prepared.preparation_ref):
            if ref not in self._inputs.bodies:
                raise EvidenceIntegrityError(
                    "Preparation body was not confirmed persisted"
                )
        self._prepared = prepared

    def discard_preparation_inputs(self) -> None:
        self._drop_inputs()

    def generation_inputs(
        self, intent: GenerationIntent, control: OperationControl
    ) -> EvidenceReader:
        if self._request is None:
            raise OwnershipConflict("Generation body handoff requires original run")
        return self._review_inputs(self._request, intent, control)

    def decision_inputs(
        self, generation: ActorGeneration, control: OperationControl
    ) -> EvidenceStore:
        control.checkpoint()
        generation = ActorGeneration.model_validate(generation)
        if (
            self._closed
            or self._thread != threading.get_ident()
            or not self._retain_inputs
            or self._request is None
            or self._input_key is None
            or self._input_key[0] != self._request
            or not self._input_key[1].matches(generation)
            or generation.status != "completed"
            or not isinstance(self._inputs, ActorContextPreparationInputs)
        ):
            raise OwnershipConflict(
                "Decision bodies require the current originally prepared generation"
            )
        return self._inputs

    def _review_inputs(
        self,
        request: ActorRunRequest,
        intent: GenerationIntent,
        control: OperationControl,
    ) -> ActorContextReviewInputs:
        control.checkpoint()
        request = ActorRunRequest.model_validate(request)
        intent = GenerationIntent.model_validate(intent)
        if (
            self._closed
            or self._thread != threading.get_ident()
            or (self._request is not None and request != self._request)
            or request.schema_version != "actor-run-request/2"
            or intent.schema_version != "actor-generation-intent/2"
            or intent.context_preparation_ref is None
            or intent.scope != request.scope
            or intent.parameters_ref not in request.parameters_refs
        ):
            raise OwnershipConflict("Actor input handoff changed original run/lifetime")
        key = (request, intent)
        if not self._retain_inputs:
            return ActorContextReviewInputs(self.evidence)
        if self._preparation_key is not None:
            if (
                self._preparation_key != (request, intent.operation, intent.request_id)
                or self._prepared is None
                or (self._prepared.input_ref, self._prepared.preparation_ref)
                != (intent.input_ref, intent.context_preparation_ref)
            ):
                raise OwnershipConflict(
                    "Generation differs from its original prepared input graph"
                )
            assert self._inputs is not None
            self._input_key = key
            self._preparation_key = None
        if self._input_key != key:
            self._drop_inputs()
            self._inputs = ActorContextReviewInputs(self.evidence)
            self._input_key = key
        assert self._inputs is not None
        return self._inputs

    def verify(
        self,
        request: ActorRunRequest,
        before: TraceSnapshot,
        intent: GenerationIntent,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> ActorPrompt:
        request = ActorRunRequest.model_validate(request)
        intent = GenerationIntent.model_validate(intent)
        if (
            intent.schema_version != "actor-generation-intent/2"
            or intent.context_preparation_ref is None
        ):
            raise OwnershipConflict("Original context-bound Actor intent required")
        evidence = self._review_inputs(request, intent, control)
        if self._reviewed is not None and self._reviewed[:4] == (
            request,
            before,
            intent,
            operation,
        ):
            # Same immutable graph and exact original trace prefix. The caller's
            # current run/claim/storage/worker authority still executes each time.
            evidence.read_verified(intent.input_ref, control)
            return self._reviewed[4]
        config = actor_context_configuration(request, evidence, control)
        receipt = read_document(
            evidence, intent.context_preparation_ref, ContextPreparationReceipt, control
        )
        recorded_public = None
        if config.policy.schema_version in (
            "context-projection-policy/2",
            "context-projection-policy/3",
        ):
            recorded_public = verified_input_document(
                evidence,
                receipt.request.source.original_ref,
                ActorPublicTurn,
                8 * 1024**2,
                control,
            )
            if self.observation_sources is None:
                raise OwnershipConflict("Adaptive original source verifier is missing")
        _, source_ref = actor_public_fact(
            request,
            before,
            operation,
            evidence,
            (
                self.observations.with_inputs(evidence)
                if isinstance(self.observations, ObservationInputReads)
                else self.observations
            ),
            control,
            sources=self.observation_sources,
            recorded=recorded_public,
        )
        expected = original_context_request(
            request,
            before,
            intent.operation,
            intent.request_id,
            source_ref,
            config,
            active_read_ref=(
                None
                if recorded_public is None or recorded_public.observation_source is None
                else recorded_public.observation_source.read_result_ref
            ),
        )
        index = len(before.project().turns)
        if (
            intent.scope != request.scope
            or intent.parameters_ref != request.parameters_refs[index]
            or intent.before_observation_ref
            != before.project().current_observation(before.plan)
        ):
            raise OwnershipConflict(
                "Context-bound Actor intent changed original scope/parameters/observation"
            )
        if receipt.outcome != "prepared" or receipt.decision is None:
            raise EvidenceIntegrityError(
                "Rejected preparation cannot dispatch an Actor generation"
            )
        prepared = PreparedContextRef(
            request_sha256=hashlib.sha256(
                expected.model_dump_json().encode()
            ).hexdigest(),
            reference=intent.context_preparation_ref,
            outcome=receipt.outcome,
            selected_input_ref=receipt.decision.selected_input_ref,
        )
        review_context(
            expected,
            prepared,
            ContextReviewDeps(
                evidence,
                _RecordedContextAuthority(expected, prepared.reference),
                self.projector,
                self.protection,
                (
                    self.counts.with_inputs(evidence)
                    if isinstance(self.counts, ContextCountInputReview)
                    else self.counts
                ),
            ),
            expected_input_ref=intent.input_ref,
            control=control,
        )
        prompt = verified_input_document(
            evidence, intent.input_ref, ActorPrompt, 8 * 1024**2, control
        )
        if self._retain_inputs:
            self._reviewed = (
                deepcopy(request),
                deepcopy(before),
                deepcopy(intent),
                deepcopy(operation),
                prompt,
            )
        if recorded_public is not None:
            self._proposal_input = (prompt, recorded_public)
        return prompt
