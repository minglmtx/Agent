"""One v2 Actor assembly over original acquired resources and existing once ports.

The source authority and trace journal remain mandatory; assembly starts no
resource, count, generation or browser action. Historical readers are separate.
"""

from lab_generate_skill.application.actor_generation_control import (
    generation_preparation_control,
)

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from lab_generate_skill.actor.decisions import RecordedActorDecisions
from lab_generate_skill.application.actor_loop import ActorLoopDeps, RecordedActorRunner
from lab_generate_skill.application.actor_model_admission import TraceActorAuthority
from lab_generate_skill.application.actor_context_inputs import (
    actor_context_configuration,
)
from lab_generate_skill.application.actor_context_preparation import (
    ControlledActorContext,
)
from lab_generate_skill.application.actor_context_review import (
    RecordedActorContextInputs,
)
from lab_generate_skill.adapters.models.actor_execution_scope import ActorExecutionScope
from lab_generate_skill.adapters.models.actor_execution_authority import (
    ResourceLocalActorAuthority,
)
from lab_generate_skill.adapters.models.local_actor import RecordedLocalActorModel
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_projection import (
    FullAxProjection,
    AdaptiveObservationProjection,
)
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.ports.observation_reads import (
    ObservationReads,
    ObservationProposalChecks,
)
from lab_generate_skill.domain.errors import OwnershipConflict, DispatchAlreadyCommitted
from lab_generate_skill.domain.local_actor import LocalActorExecution, LocalActorCall
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.ports.actor import ActorRunAuthority
from lab_generate_skill.ports.browser import BrowserActions
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import (
    OperationControls,
    OperationControl,
    Clock,
)
from lab_generate_skill.ports.trace_journal import (
    TraceJournal,
    TraceGenerationInputHandoff,
    TraceReadingInputHandoff,
    TraceReadingInputs,
)
from .actor_projection import build_actor_projection
from .actor_context_runtime import live_actor_context


class RetainedActorReturns:
    def __init__(
        self, original: TraceActorAuthority, completed: list[LocalActorExecution]
    ) -> None:
        self.original, self.completed = original, completed

    def verify(
        self,
        call: LocalActorCall,
        prompt: ActorPrompt,
        parameters: LocalActorParameters,
        guard: ProcessOwnerGuard,
        phase: Literal["preflight", "dispatch"],
        control: OperationControl,
    ) -> None:
        self.original.verify(call, prompt, parameters, guard, phase, control)

    def verify_return(
        self, execution: LocalActorExecution, control: OperationControl
    ) -> None:
        self.original.verify_return(execution, control)
        for previous in self.completed:
            if previous.call.key == execution.call.key:
                if previous != execution:
                    raise OwnershipConflict("Original Actor return identity changed")
                return
        self.completed.append(execution)


@dataclass(frozen=True)
class OriginalActorRuntime:
    runner: RecordedActorRunner
    preparation: ControlledActorContext
    input_review: RecordedActorContextInputs
    model: RecordedLocalActorModel


def original_actor_runtime(
    request: ActorRunRequest,
    journal: TraceJournal,
    scope: ActorExecutionScope,
    browser: BrowserActions,
    evidence: EvidenceStore,
    controls: OperationControls,
    clock: Clock,
    authority: ActorRunAuthority,
    calls_root: Path,
    completed: list[LocalActorExecution],
) -> OriginalActorRuntime:
    request = ActorRunRequest.model_validate(request)
    if request.schema_version != "actor-run-request/2":
        raise ValueError(
            "Current Actor assembly requires explicit v2 context; no legacy fallback"
        )
    if any(
        v is None
        for v in (
            journal,
            scope,
            browser,
            evidence,
            controls,
            clock,
            authority,
            completed,
        )
    ):
        raise ValueError(
            "Original Actor assembly requires all resource/source dependencies"
        )
    if (
        not isinstance(calls_root, Path)
        or not calls_root.is_absolute()
        or type(completed) is not list
        or completed
    ):
        raise ValueError(
            "Original absolute call root and fresh return collection required"
        )
    controls.bind(request.operation).checkpoint()
    read = request.operation.model_copy(
        update={
            "operation_id": "actor-assembly-read-"
            + hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        }
    )
    before = TraceSnapshot.model_validate(journal.read(read))
    view = before.project()
    if (
        before.events
        or view.sealed is not None
        or view.intent is not None
        or view.halted
    ):
        raise DispatchAlreadyCommitted(
            "Original Actor assembly cannot resume pending/used trace"
        )
    if (
        before.plan.scope != request.scope
        or before.plan.initial_observation_ref != request.initial_observation_ref
        or before.plan.max_generations != len(request.parameters_refs)
        or scope.binding.resource != request.model_allocation
        or scope.binding.cleanup_seconds != request.cleanup_seconds
    ):
        raise OwnershipConflict("Actor assembly changed original trace/resource/budget")
    config = actor_context_configuration(
        request, evidence, controls.bind(request.operation)
    )
    project = (
        prepare_actor
        if isinstance(config.policy.actor_projection, AdaptiveObservationProjection)
        else build_actor_projection(
            config.policy.actor_projection or FullAxProjection()
        )
    )
    observations = EvidenceObservations(evidence, controls)
    preparation, input_review = live_actor_context(
        request,
        scope.spec,
        scope.engine,
        journal,
        evidence,
        observations,
        authority,
        controls,
        control=controls.bind(request.operation),
    )
    if isinstance(journal, TraceGenerationInputHandoff):
        journal = journal.with_generation_inputs(input_review)
    readings = None
    sources = preparation.observation_sources
    if sources is not None:
        if (
            not isinstance(sources, ObservationReads)
            or not isinstance(sources, TraceReadingInputs)
            or not isinstance(journal, TraceReadingInputHandoff)
        ):
            raise OwnershipConflict(
                "Adaptive original runtime requires actual reader and original journal proof handoff"
            )
        journal = journal.with_reading_inputs(sources)
        readings = sources
    original = TraceActorAuthority(
        request,
        journal,
        evidence,
        observations,
        project,
        authority,
        controls,
        context=input_review,
        inputs=input_review,
    )
    business = RetainedActorReturns(original, completed)
    model = RecordedLocalActorModel(
        calls_root,
        scope.binding,
        scope.engine,
        evidence,
        controls,
        ResourceLocalActorAuthority(scope, business, inputs=input_review),
        inputs=input_review,
        clock=clock,
        prepare_control=generation_preparation_control,
    )
    runner = RecordedActorRunner(
        ActorLoopDeps(
            journal,
            evidence,
            observations,
            model,
            browser,
            RecordedActorDecisions(
                evidence,
                controls,
                inputs=input_review,
                proposals=(
                    sources if isinstance(sources, ObservationProposalChecks) else None
                ),
            ),
            project,
            authority,
            controls,
            clock,
            context=preparation,
            readings=readings,
        )
    )
    return OriginalActorRuntime(runner, preparation, input_review, model)
