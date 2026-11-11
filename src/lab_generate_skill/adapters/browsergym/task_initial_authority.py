"""Read-only initial qualification against the original unique browser return."""

from collections.abc import Callable
from lab_generate_skill.adapters.sites.task_resource_owner import (
    OriginalTaskResourceOwner,
)
from lab_generate_skill.adapters.browsergym.worker_client import (
    SupervisedBrowserSession,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.initial_observation import InitialObservationChecks
from lab_generate_skill.ports.lifecycle import OperationControl


class OriginalTaskInitialAuthority:
    def __init__(
        self,
        resources: OriginalTaskResourceOwner,
        checks: Callable[[], InitialObservationChecks],
    ) -> None:
        if not isinstance(resources, OriginalTaskResourceOwner) or not callable(checks):
            raise TypeError("Original task resource and initial checks required")
        self.resources, self.checks = resources, checks

    def verify(
        self,
        inputs: InitialObservationInputs,
        checks: StateChecks,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        b = self.resources.require_browser(operation, control)
        inputs = InitialObservationInputs.model_validate(inputs)
        engine = b.session.engine
        if (
            not isinstance(engine, SupervisedBrowserSession)
            or engine.configuration_reply is None
        ):
            raise OwnershipConflict("Original guarded browser configuration required")
        if (
            inputs.browser != b.spec
            or inputs.selection.browser_acquired_ref != b.session.resource_started_ref
            or inputs.acquired.details.started.initial_observation_ref
            != b.session.observation_ref
            or inputs.observation.record.sequence != 0
            or inputs.acquired.details.started.owner_guard
            != engine.configuration_reply.owner_guard
        ):
            raise OwnershipConflict(
                "Initial checks changed original unique browser return"
            )
        if checks != self.checks().check(inputs, control):
            raise OwnershipConflict(
                "Initial checks differ from original complete measurements"
            )
