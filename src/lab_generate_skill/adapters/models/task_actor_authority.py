"""Original live model/browser/initial handoff for the existing Actor loop."""

from collections.abc import Callable
from lab_generate_skill.adapters.sites.task_initialized_inputs import (
    initialized_candidate_inputs,
)
from lab_generate_skill.adapters.sites.task_resource_owner import (
    OriginalTaskResourceOwner,
)
from lab_generate_skill.adapters.sites.task_initialization import (
    RecordedTaskInitialization,
)
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.trace_journal import TraceJournal


class OriginalTaskActorAuthority:
    def __init__(
        self,
        resources: OriginalTaskResourceOwner,
        initialization: Callable[[], RecordedTaskInitialization],
        trace: Callable[[], TraceJournal],
    ) -> None:
        if (
            not isinstance(resources, OriginalTaskResourceOwner)
            or not callable(initialization)
            or not callable(trace)
        ):
            raise TypeError("Original task/initialization/trace suppliers required")
        self.resources, self.initialization, self.trace = (
            resources,
            initialization,
            trace,
        )

    def verify(
        self,
        request: ActorRunRequest,
        snapshot: TraceSnapshot,
        control: OperationControl,
    ) -> None:
        request, snapshot = ActorRunRequest.model_validate(
            request
        ), TraceSnapshot.model_validate(snapshot)
        r, initial = self.resources, self.initialization()
        s = initial.state
        if (
            initial.plan != r.plan
            or s.phase != "initialized"
            or s.result is None
            or s.result.actor != request
            or s.equivalence_ref is None
            or s.baseline_ref is None
            or request.model_allocation != r.model.binding.resource
            or snapshot.plan.binding != r.plan.intent.binding
            or snapshot.plan.scope != request.scope
            or snapshot.plan.initial_observation_ref != request.initial_observation_ref
        ):
            raise OwnershipConflict(
                "Actor changed original initialized request/model/trace"
            )
        b = r.require_browser(request.operation, control)
        if (
            request.browser_allocation != b.spec.token
            or self.trace().read(r.plan.read_operation) != snapshot
            or snapshot.project().current_observation(snapshot.plan)
            != b.session.observation_ref
        ):
            raise OwnershipConflict("Actor changed original live browser/trace view")
        held = initial.inputs
        if held is None:
            baseline = initial.states.load_baseline(s.baseline_ref, request.operation)
            equivalence = initial.contexts.load_equivalence(
                s.equivalence_ref, request.operation
            )
        else:
            facts = initialized_candidate_inputs(
                initial,
                s.equivalence_ref,
                initial.plan.skill_ref,
                request.operation,
                control,
            )
            baseline, equivalence = facts.baseline, facts.equivalence
        if (
            baseline != s.baseline
            or equivalence != s.equivalence
            or baseline.status != "ready"
            or equivalence.status != "equivalent"
        ):
            raise OwnershipConflict(
                "Actor requires original ready and actually equivalent initial state"
            )
