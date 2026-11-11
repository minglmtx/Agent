"""Compare actual source/candidate contents without equating physical identities.

Original state/source authorities still verify the complete readiness and Reset
graphs. This consumer reads their exact snapshot selections, never caller paths
or current mutable services, and cannot grant a dispatch or repeat a measurement.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .navigation_equivalence_inputs import NavigationComparisonInputs

from lab_generate_skill.domain.baseline import BaselineInputs
from lab_generate_skill.domain.initial_adoption import InitialAdoptionInputs
from lab_generate_skill.domain.public_context import PublicContextInputs
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.domain.evaluation import CheckResult
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from .navigation_contents_schema import NavigationContents
from .navigation_equivalence_contents import NavigationEquivalenceContents
from .navigation_recovery_contract import NavigationRecoverySnapshot
from .navigation_state_checks import NavigationStateChecks
from .navigation_state_policy import navigation_initial_state_spec


class NavigationInitialComparison:
    def __init__(self, store: EvidenceReader) -> None:
        self.store = store
        self.reader = NavigationStateChecks(store)

    def read_comparison(
        self,
        source: PublicContextInputs,
        candidate: BaselineInputs,
        control: OperationControl,
    ) -> "NavigationComparisonInputs":
        from .navigation_equivalence_inputs import NavigationComparisonInputs

        return NavigationComparisonInputs.read_original(
            self.store, source, candidate, control
        )

    def contents(
        self, inputs: BaselineInputs, control: OperationControl
    ) -> tuple[NavigationContents | NavigationEquivalenceContents, EvidenceRef]:
        references = {
            ref
            for check in inputs.environment.checks.checks
            for ref in check.evidence
            if ref.content_schema == "environment-selection/1"
        }
        if len(references) != 1:
            raise OwnershipConflict("One original environment selection is required")
        reference = next(iter(references))
        selection = self.reader.read(
            reference, "environment-selection/1", EnvironmentSelection, control
        )
        raw = self.store.read(selection.snapshot_ref, control=control)
        require_complete_bytes(selection.snapshot_ref, raw)
        if (
            selection.snapshot_ref.content_schema,
            selection.snapshot_ref.visibility,
            selection.snapshot_ref.media_type,
        ) != ("admin-navigation-recovery/1", "private", "application/json"):
            raise OwnershipConflict("Private original navigation snapshot required")
        saved = NavigationRecoverySnapshot.model_validate_json(raw)
        if saved.model_dump_json().encode() != raw:
            raise OwnershipConflict("Canonical original navigation snapshot required")
        request = saved.request
        scope = inputs.prepared.scope
        if (
            selection.scope != scope
            or selection.spec_ref != inputs.spec_ref
            or request.task != scope.task
            or (
                request.operation.run_id,
                request.operation.owner_id,
                request.operation.attempt_id,
            )
            != (scope.owner.run_id, scope.owner.owner_id, scope.attempt_id)
            or request.binding_ref != inputs.preparation.task_binding_ref
            or saved.state.digest != inputs.environment.measured_state_sha256
            or saved.contents is None
        ):
            raise OwnershipConflict(
                "Original same-scope snapshot with actual contents is required"
            )
        saved.contents.require_snapshot(saved.state)
        return saved.contents, selection.snapshot_ref

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
        source = PublicContextInputs.model_validate(source)
        candidate = BaselineInputs.model_validate(candidate)
        control.checkpoint()
        original = source.baseline_inputs
        scope = candidate.prepared.scope
        if (
            candidate.spec != navigation_initial_state_spec(scope.task)
            or original.spec != candidate.spec
            or source.baseline.status != "ready"
            or source.reset.status != "safe"
            or source.reset.scope != original.prepared.scope
            or source.baseline.scope != original.prepared.scope
            or (adoption is None and scope.owner != original.prepared.scope.owner)
            or scope.attempt_id == original.prepared.scope.attempt_id
            or scope.task != original.prepared.scope.task
            or source.context.task != candidate.public_task
        ):
            raise OwnershipConflict(
                "Qualified original Admin navigation source and distinct same-owner attempt required"
            )
        for inputs in (original, candidate):
            observed = inputs.observation
            if (
                observed.sequence != 0
                or observed.state != "ready"
                or observed.last_action_error
                or len(observed.tabs) != 1
                or observed.tabs[0].url != inputs.public_task.start_url
                or observed.attempt_id != inputs.prepared.scope.attempt_id
                or observed.context_id != inputs.prepared.scope.context_id
                or inputs.environment.checks.required != inputs.spec.environment_checks
                or inputs.initial.checks.required != inputs.spec.initial_checks
                or inputs.environment.checks.status != "pass"
                or inputs.preparation.checks.status != "pass"
                or inputs.initial.checks.status != "pass"
            ):
                raise OwnershipConflict(
                    "Complete original ready initial measurements required"
                )
        left, left_ref = self.contents(original, control)
        right, right_ref = self.contents(candidate, control)
        if not isinstance(left, NavigationEquivalenceContents) or not isinstance(
            right, NavigationEquivalenceContents
        ):
            raise OwnershipConflict(
                "Version3 held-search metadata projection required for initial equivalence"
            )
        equal = left.equivalence_sha256 == right.equivalence_sha256
        control.checkpoint()
        return StateChecks(
            required=candidate.spec.equivalence_checks,
            checks=(
                CheckResult(
                    name="admin.navigation.initial.equivalence",
                    status="pass" if equal else "fail",
                    reason_code=(
                        "ORIGINAL_ADMIN_CONTENTS_EQUAL"
                        if equal
                        else "ORIGINAL_ADMIN_CONTENTS_DIFFER"
                    ),
                    evidence=(
                        source.baseline_ref,
                        original.environment_ref,
                        original.initial_ref,
                        left_ref,
                        candidate.environment_ref,
                        candidate.initial_ref,
                        right_ref,
                    ),
                ),
            ),
        )
