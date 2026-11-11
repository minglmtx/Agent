"""Shared typed task inputs/resources/authorities; no launch defaults or rights."""

from lab_generate_skill.adapters.sites.task_initialization_inputs import (
    TaskInitializationInputs,
)


from collections.abc import Callable
from dataclasses import dataclass
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.ports.site_handle import SiteHandle
from lab_generate_skill.ports.actor import ActorRunAuthority
from lab_generate_skill.adapters.sites.task_site_authority import TaskSiteAuthority
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.domain.actor_admission import PreparedActorInput
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.task_capture import TaskCapturePlan
from lab_generate_skill.domain.task_execution import TaskExecutionPlan, InitializedTask
from lab_generate_skill.domain.task_finalization import TaskFinalizationPlan
from lab_generate_skill.domain.task_initialization import TaskInitializationPlan
from lab_generate_skill.domain.task_preparation import SiteTaskPreparationPlan
from lab_generate_skill.ports.browser_capture import BrowserCaptureAuthority
from lab_generate_skill.ports.initial_adoption import InitialAdoptionAuthority
from lab_generate_skill.ports.contexts import ContextAuthority
from lab_generate_skill.ports.initial_observation import InitialObservationAuthority
from lab_generate_skill.ports.lifecycle import ResourceJournal, OperationControl
from lab_generate_skill.ports.state_records import StateAuthority
from lab_generate_skill.ports.task_bindings import TaskBindings
from lab_generate_skill.ports.task_finalization import (
    TaskFinalizationAuthority,
    UnstartedTaskBrowserAuthority,
)
from lab_generate_skill.ports.trace_journal import TraceJournal
from .task_actor import TaskActorResources


@dataclass(frozen=True)
class TaskExecutionDeclarations:
    plan: TaskExecutionPlan
    preparation: SiteTaskPreparationPlan
    reset: ResetPlan
    capture: TaskCapturePlan
    capture_ref: EvidenceRef
    finalization: TaskFinalizationPlan
    finalization_ref: EvidenceRef


@dataclass(frozen=True)
class TaskInitialBinding:
    """Freeze actual prepared refs before acquisition; no predicted seq0/baseline."""

    declaration: TaskInitializationPlan
    declaration_ref: EvidenceRef
    browser: RetainedBrowserResource
    state: StateAuthority
    context: ContextAuthority
    capture: BrowserCaptureAuthority
    initial: InitialObservationAuthority
    inputs: TaskInitializationInputs | None = None
    adoption_checks: InitialAdoptionAuthority | None = None

    def complete(self) -> bool:
        """Check required bindings and the optional body carrier, never authority."""
        return (
            all(
                value is not None
                for value in (
                    self.declaration,
                    self.declaration_ref,
                    self.browser,
                    self.state,
                    self.context,
                    self.capture,
                    self.initial,
                )
            )
            and (
                self.inputs is None or isinstance(self.inputs, TaskInitializationInputs)
            )
            and (
                self.adoption_checks is None
                or isinstance(self.adoption_checks, InitialAdoptionAuthority)
            )
        )


@dataclass(frozen=True)
class TaskExecutionResources:
    site_spec: SiteResourceSpec
    site: SiteHandle
    site_journal: ResourceJournal
    browser_journal: ResourceJournal
    bindings: TaskBindings
    browser: Callable[[], RetainedBrowserResource | None]
    trace: Callable[[], TraceJournal]
    # This trusted factory must retain any partially constructed owner in
    # browser(), even if it fails before returning binding. No acquisition here.
    initialization: Callable[
        [RecordedSiteTaskPreparation, OperationContext, OperationControl],
        TaskInitialBinding,
    ]
    actor: Callable[[InitializedTask, PreparedActorInput], TaskActorResources]
    native_source: TaskSiteAuthority


@dataclass(frozen=True)
class TaskExecutionAuthorities:
    finalization: TaskFinalizationAuthority
    unstarted: UnstartedTaskBrowserAuthority


@dataclass(frozen=True)
class ExecutionTaskAuthorities(TaskExecutionAuthorities):
    """Single-task actual Actor source rights, absent from construction runtime."""

    actor_source: ActorRunAuthority


from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.browser_capture import BrowserCaptureRequest
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration


class OriginalTaskInitialBinding:
    """One owner-local composition value, never resource/request history."""

    def __init__(self) -> None:
        self.value: TaskInitialBinding | None = None

    def original(self) -> TaskInitialBinding:
        if self.value is None:
            raise OwnershipConflict("Original initial binding not constructed")
        return self.value

    def verify_capture(
        self,
        configuration: BrowserWorkerConfiguration,
        request: BrowserCaptureRequest,
        intent_ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        self.original().capture.verify_capture(
            configuration, request, intent_ref, control
        )
