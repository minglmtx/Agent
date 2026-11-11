"""One original category initial return, with no prior Actor actions."""

from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.shopping_navigation_browser_initialization import (
    ShoppingCategoryInitialization,
)
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.evaluation import CheckResult
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from .navigation_policy import category_navigation_initial_spec


class CategoryNavigationInitialObservationChecks:
    def check(
        self, inputs: InitialObservationInputs, control: OperationControl
    ) -> StateChecks:
        inputs = InitialObservationInputs.model_validate(inputs)
        control.checkpoint()
        selected = inputs.browser.configuration.initialization
        if not isinstance(selected, ShoppingCategoryInitialization):
            raise ValueError("Explicit original category initialization required")
        selected.check(inputs.browser.configuration.spec)
        spec = category_navigation_initial_spec(inputs.prepared.scope.task)
        if (
            selected.prepared_ref != inputs.selection.preparation.prepared_ref
            or inputs.spec != spec
        ):
            raise OwnershipConflict(
                "Category initial observation changed original preparation/policy"
            )
        view, returned = inputs.observation.record, inputs.returned
        ready = (
            view.state == "ready"
            and not view.last_action_error
            and len(view.tabs) == 1
            and view.tabs[0].url == inputs.prepared.public_task.start_url
            and bool(inputs.observation.text)
            and not (
                returned.terminated or returned.truncated or returned.protocol_terminal
            )
            and not any(
                e.kind in ("before_action", "after_action") for e in returned.events
            )
        )
        control.checkpoint()
        return StateChecks(
            required=spec.initial_checks,
            checks=(
                CheckResult(
                    name=spec.initial_checks[0],
                    status="pass" if ready else "fail",
                    reason_code=(
                        "ORIGINAL_CATEGORY_INITIAL_VIEW"
                        if ready
                        else "CATEGORY_INITIAL_VIEW_NOT_READY"
                    ),
                    evidence=(
                        inputs.selection.browser_acquired_ref,
                        inputs.acquired.details.started.initial_return_ref,
                    ),
                ),
            ),
        )
