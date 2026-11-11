"""Consume the original one root observation, never log in or observe again."""

from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabSshKeyInitialization,
)
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.evaluation import CheckResult
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from .ssh_key_policy import ssh_key_initial_spec, INITIAL_CHECKS


class SshKeyInitialObservationChecks:
    def check(
        self, inputs: InitialObservationInputs, control: OperationControl
    ) -> StateChecks:
        inputs = InitialObservationInputs.model_validate(inputs)
        control.checkpoint()
        selected = inputs.browser.configuration.initialization
        if not isinstance(selected, GitlabSshKeyInitialization):
            raise ValueError("Explicit original SSH browser initialization required")
        selected.check(inputs.browser.configuration.spec)
        if selected.prepared_ref != inputs.selection.preparation.prepared_ref:
            raise OwnershipConflict("SSH browser changed original preparation")
        if inputs.spec != ssh_key_initial_spec(inputs.prepared.scope.task):
            raise ValueError("Unsupported SSH initial observation coverage")
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
            required=INITIAL_CHECKS,
            checks=(
                CheckResult(
                    name=INITIAL_CHECKS[0],
                    status="pass" if ready else "fail",
                    reason_code=(
                        "ORIGINAL_GITLAB_ROOT_VIEW"
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
