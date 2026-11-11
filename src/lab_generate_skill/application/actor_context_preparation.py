"""Controlled context step in the existing Actor loop; no intent/send/new ledger."""

from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_context import ActorPreparedInput
from lab_generate_skill.domain.context_preparation import (
    ContextPreparationRequest,
    PreparedContextRef,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.ports.actor import ActorRunAuthority
from lab_generate_skill.ports.actor_context import (
    ActorContextInputLifetime,
    ActorContextPreparationInputHandoff,
    ActorObservationSources,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.observations import Observations, ObservationInputReads
from lab_generate_skill.ports.trace_journal import TraceJournal
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.ports.context_projection import (
    ContextInputProjector,
    ContextProtectionVerifier,
    ContextTokenCounter,
    ContextTokenInputMeasure,
)
from .actor_context_inputs import (
    actor_context_configuration,
    actor_public_fact,
    original_context_request,
    PUBLIC_ACTOR_CONTEXT,
)
from .context_preparation import ContextPreparationDeps, prepare_context
from .context_evidence import publish_raw


class ActorContextRejected(RuntimeError):
    def __init__(self, prepared: PreparedContextRef) -> None:
        self.prepared = prepared
        super().__init__(
            "Actor input preparation refused; original private receipt "
            + prepared.reference.model_dump_json()
        )


class _LiveContextAuthority:
    def __init__(
        self,
        expected: ContextPreparationRequest,
        original: ActorRunRequest,
        before: TraceSnapshot,
        journal: TraceJournal,
        authority: ActorRunAuthority,
        controls: OperationControls,
    ) -> None:
        self.expected, self.original, self.before = expected, original, before
        self.journal, self.authority, self.controls = journal, authority, controls

    def verify_prepare(
        self, request: ContextPreparationRequest, *, control: OperationControl
    ) -> None:
        self.controls.bind(self.original.operation).checkpoint()
        self.controls.bind(request.operation).checkpoint()
        if (
            request != self.expected
            or self.journal.read(request.operation) != self.before
        ):
            raise OwnershipConflict(
                "Original Actor preparation/trace changed or became pending"
            )
        self.authority.verify(self.original, self.before, control)
        control.checkpoint()

    def verify_recorded(
        self,
        request: ContextPreparationRequest,
        reference: EvidenceRef,
        *,
        control: OperationControl,
    ) -> None:
        raise OwnershipConflict(
            "Live preparation authority is not historical review authority"
        )


class ControlledActorContext:
    def __init__(
        self,
        request: ActorRunRequest,
        journal: TraceJournal,
        evidence: EvidenceStore,
        observations: Observations,
        authority: ActorRunAuthority,
        controls: OperationControls,
        projector: ContextInputProjector,
        protection: ContextProtectionVerifier,
        counter: ContextTokenCounter,
        *,
        inputs: ActorContextInputLifetime | None = None,
        observation_sources: ActorObservationSources | None = None,
    ) -> None:
        self.request = ActorRunRequest.model_validate(request)
        if self.request.schema_version != "actor-run-request/2":
            raise ValueError("Controlled Actor context requires explicit v2 request")
        self.journal, self.evidence, self.observations = journal, evidence, observations
        self.authority, self.controls = authority, controls
        self.projector, self.protection, self.counter = projector, protection, counter
        self.inputs = inputs
        self.observation_sources = observation_sources

    def clear_inputs(self) -> None:
        if self.observation_sources is not None:
            self.observation_sources.clear_inputs()
        if self.inputs is not None:
            self.inputs.clear_inputs()

    def prepare(
        self,
        request: ActorRunRequest,
        before: TraceSnapshot,
        operation: OperationContext,
        request_id: str,
        *,
        control: OperationControl,
    ) -> ActorPreparedInput:
        handoff = (
            self.inputs
            if isinstance(self.inputs, ActorContextPreparationInputHandoff)
            else None
        )
        evidence = (
            self.evidence
            if handoff is None
            else handoff.preparation_inputs(
                request, operation, request_id, self.evidence, control
            )
        )
        try:
            result = self._prepare(
                request,
                before,
                operation,
                request_id,
                control=control,
                evidence=evidence,
            )
            if handoff is not None:
                handoff.prepared_inputs(result, control)
            return result
        except BaseException:
            if handoff is not None:
                handoff.discard_preparation_inputs()
            raise

    def _prepare(
        self,
        request: ActorRunRequest,
        before: TraceSnapshot,
        operation: OperationContext,
        request_id: str,
        *,
        control: OperationControl,
        evidence: EvidenceStore,
    ) -> ActorPreparedInput:
        request = ActorRunRequest.model_validate(request)
        before = TraceSnapshot.model_validate(before)
        if request != self.request:
            raise OwnershipConflict("Actor context changed original run request")
        self.controls.bind(request.operation).checkpoint()
        self.controls.bind(operation).checkpoint()
        config = actor_context_configuration(request, evidence, control)
        # Refuse a pending/changed trace before even saving public source bytes.
        if self.journal.read(operation) != before:
            raise OwnershipConflict("Actor trace changed before preparation")
        self.authority.verify(request, before, control)
        raw, source_ref = actor_public_fact(
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
        )
        from lab_generate_skill.domain.actor_prompt import ActorPublicTurn

        public = ActorPublicTurn.model_validate_json(raw)
        expected = original_context_request(
            request,
            before,
            operation,
            request_id,
            source_ref,
            config,
            active_read_ref=(
                None
                if public.observation_source is None
                else public.observation_source.read_result_ref
            ),
        )
        gate = _LiveContextAuthority(
            expected, request, before, self.journal, self.authority, self.controls
        )
        gate.verify_prepare(expected, control=control)
        retained: list[EvidenceRef] = []
        try:
            metadata = PUBLIC_ACTOR_CONTEXT.model_copy(
                update={"content_schema": public.schema_version}
            )
            actual = publish_raw(evidence, raw, metadata, retained, control)
            if actual != source_ref:
                raise EvidenceIntegrityError(
                    "Actor public source publication changed identity"
                )
        except BaseException as error:
            setattr(error, "actor_context_source_candidates", tuple(retained))
            raise
        prepared = prepare_context(
            expected,
            ContextPreparationDeps(
                evidence,
                gate,
                self.projector,
                self.protection,
                (
                    self.counter.with_inputs(evidence)
                    if isinstance(self.counter, ContextTokenInputMeasure)
                    else self.counter
                ),
            ),
            control=control,
        )
        if prepared.outcome != "prepared" or prepared.selected_input_ref is None:
            raise ActorContextRejected(prepared)
        return ActorPreparedInput(
            input_ref=prepared.selected_input_ref, preparation_ref=prepared.reference
        )
