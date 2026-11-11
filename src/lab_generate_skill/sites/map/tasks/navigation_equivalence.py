"""Selected plain/Communities navigation initial equivalence, not goal success.

Source/candidate baseline authorities must independently validate complete native
state and original readiness. This derived comparison never becomes native data.
"""

from lab_generate_skill.domain.baseline import BaselineInputs
from lab_generate_skill.domain.initial_adoption import InitialAdoptionInputs
from lab_generate_skill.domain.public_context import PublicContextInputs
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.evaluation import CheckResult
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.map_navigation_scope import NAVIGATION_PAGE_MEMBERS
from lab_generate_skill.ports.lifecycle import OperationControl
from ..navigation_initial_rules import same_start_document


class NavigationInitialComparison:
    def compare(
        self,
        source: PublicContextInputs,
        candidate: BaselineInputs,
        control: OperationControl,
    ) -> StateChecks:
        return self._compare(source, candidate, control, None)

    def compare_adopted(
        self,
        source: PublicContextInputs,
        candidate: BaselineInputs,
        adoption: InitialAdoptionInputs,
        control: OperationControl,
    ) -> StateChecks:
        adoption = InitialAdoptionInputs.model_validate(adoption)
        adoption.require_comparison(source, candidate)
        return self._compare(source, candidate, control, adoption)

    def _compare(
        self,
        source: PublicContextInputs,
        candidate: BaselineInputs,
        control: OperationControl,
        adoption: InitialAdoptionInputs | None,
    ) -> StateChecks:
        control.checkpoint()
        original = source.baseline_inputs
        task = candidate.public_task.identity
        if (
            (task.site, task.family, task.contract_version, task.split)
            != ("map", "navigation_page_identity", 1, "train")
            or task.source_task_id not in NAVIGATION_PAGE_MEMBERS
            or (
                adoption is None
                and candidate.prepared.scope.owner != source.baseline.scope.owner
            )
            or candidate.prepared.scope.attempt_id == source.baseline.scope.attempt_id
            or candidate.prepared.scope.task != source.baseline.scope.task
            or source.context.task != candidate.public_task
            or original.spec != candidate.spec
            or candidate.spec.equivalence_checks
            != ("map.navigation.initial.equivalence",)
        ):
            raise OwnershipConflict(
                "Exact selected navigation source/candidate contract required"
            )
        for inputs in (original, candidate):
            observed = inputs.observation
            if (
                observed.sequence != 0
                or observed.state != "ready"
                or observed.last_action_error
                or len(observed.tabs) != 1
                or not same_start_document(inputs.public_task, observed.tabs[0].url)
                or inputs.initial.checks.status != "pass"
                or inputs.environment.checks.status != "pass"
            ):
                raise OwnershipConflict(
                    "Original complete ready initial measurements required"
                )
        matches = (
            original.environment.measured_state_sha256
            == candidate.environment.measured_state_sha256
        )
        control.checkpoint()
        return StateChecks(
            required=candidate.spec.equivalence_checks,
            checks=(
                CheckResult(
                    name="map.navigation.initial.equivalence",
                    status="pass" if matches else "fail",
                    reason_code=(
                        "ORIGINAL_READY_NAVIGATION_AND_COMPLETE_STATE_EQUAL"
                        if matches
                        else "ORIGINAL_COMPLETE_STATE_DIFFERS"
                    ),
                    evidence=(
                        source.baseline_ref,
                        original.environment_ref,
                        original.initial_ref,
                        candidate.environment_ref,
                        candidate.initial_ref,
                    ),
                ),
            ),
        )
