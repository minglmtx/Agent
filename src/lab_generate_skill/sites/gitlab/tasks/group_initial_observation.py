"""Consume exactly the declared original Group view, never query or observe again."""

from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabGroupInitialization,
)
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.evaluation import CheckResult
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.task_families.document_health import is_error_document
from .group_policy import group_initial_spec, INITIAL_CHECKS


class GroupInitialObservationChecks:
    def check(
        self, inputs: InitialObservationInputs, control: OperationControl
    ) -> StateChecks:
        inputs = InitialObservationInputs.model_validate(inputs)
        control.checkpoint()
        selected = inputs.browser.configuration.initialization
        if not isinstance(selected, GitlabGroupInitialization):
            raise ValueError("Explicit original Group browser initialization required")
        selected.check(inputs.browser.configuration.spec)
        if selected.prepared_ref != inputs.selection.preparation.prepared_ref:
            raise OwnershipConflict("Group browser changed original preparation")
        if inputs.spec != group_initial_spec(inputs.prepared.scope.task):
            raise ValueError("Unsupported Group initial observation coverage")
        view, returned = inputs.observation.record, inputs.returned
        ready = (
            view.state == "ready"
            and not view.last_action_error
            and len(view.tabs) == 1
            and view.tabs[0].url == inputs.prepared.public_task.start_url
            and not is_error_document(view.tabs[0].url, None, view.tabs[0].title)
            and bool((inputs.observation.text or "").strip())
            and not (
                returned.terminated or returned.truncated or returned.protocol_terminal
            )
            and not any(
                e.kind in ("before_action", "after_action") for e in returned.events
            )
        )
        control.checkpoint()
        return StateChecks(
            required=INITIAL_CHECKS,
            checks=(
                CheckResult(
                    name=INITIAL_CHECKS[0],
                    status="pass" if ready else "fail",
                    reason_code=(
                        (
                            "ORIGINAL_GITLAB_GROUP_FORM_VIEW"
                            if selected.start_path != "/"
                            else "ORIGINAL_GITLAB_GROUP_ROOT_VIEW"
                        )
                        if ready
                        else "INITIAL_GITLAB_VIEW_NOT_READY"
                    ),
                    evidence=(
                        inputs.selection.browser_acquired_ref,
                        inputs.acquired.details.started.initial_return_ref,
                    ),
                ),
            ),
        )
