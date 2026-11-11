"""Measured sole declared-start view; trajectory equivalence remains independent."""

from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.admin_navigation_browser_initialization import (
    AdminNavigationInitialization,
)
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.evaluation import CheckResult
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl

NAVIGATION_INITIAL_CHECKS = ("admin.navigation.initial.observation",)


class NavigationInitialObservationChecks:
    def check(
        self, inputs: InitialObservationInputs, control: OperationControl
    ) -> StateChecks:
        inputs = InitialObservationInputs.model_validate(inputs)
        control.checkpoint()
        choice = inputs.browser.configuration.initialization
        if not isinstance(choice, AdminNavigationInitialization):
            raise ValueError("Explicit Admin navigation initialization required")
        choice.check(inputs.browser.configuration.spec)
        if choice.prepared_ref != inputs.selection.preparation.prepared_ref:
            raise OwnershipConflict(
                "Initial browser selection changed original preparation"
            )
        if inputs.spec.initial_checks != NAVIGATION_INITIAL_CHECKS:
            raise ValueError(
                "Unsupported Admin navigation initial observation coverage"
            )
        observed = inputs.observation.record
        ready = (
            observed.state == "ready"
            and not observed.last_action_error
            and len(observed.tabs) == 1
            and observed.tabs[0].url == inputs.prepared.public_task.start_url
            and bool(inputs.observation.text)
            and not (
                inputs.returned.terminated
                or inputs.returned.truncated
                or inputs.returned.protocol_terminal
            )
            and not any(
                e.kind in ("before_action", "after_action")
                for e in inputs.returned.events
            )
        )
        control.checkpoint()
        return StateChecks(
            required=NAVIGATION_INITIAL_CHECKS,
            checks=(
                CheckResult(
                    name=NAVIGATION_INITIAL_CHECKS[0],
                    status="pass" if ready else "fail",
                    reason_code=(
                        "ORIGINAL_INITIAL_VIEW" if ready else "INITIAL_VIEW_NOT_READY"
                    ),
                    evidence=(
                        inputs.selection.browser_acquired_ref,
                        inputs.acquired.details.started.initial_return_ref,
                    ),
                ),
            ),
        )
