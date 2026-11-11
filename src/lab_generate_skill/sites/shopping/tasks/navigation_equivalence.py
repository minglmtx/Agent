"""Existing initial-comparison port over exact persisted original snapshots.

Only four original selections/snapshots are read, once each in this call. No
current site operation, cached permission, new snapshot or dispatch is granted.
The enclosing source/initialization authorities still validate complete graphs.
"""

import hashlib
from lab_generate_skill.domain.baseline import BaselineInputs
from lab_generate_skill.domain.public_context import PublicContextInputs
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.domain.evaluation import CheckResult
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from .navigation_contents import NavigationContents
from .navigation_recovery import CategoryNavigationRecoverySnapshot
from .navigation_policy import category_navigation_initial_spec


class CategoryNavigationInitialComparison:
    def __init__(self, store: EvidenceReader) -> None:
        self.store = store

    def contents(
        self, inputs: BaselineInputs, control: OperationControl
    ) -> tuple[NavigationContents, EvidenceRef]:
        references = {
            ref
            for check in inputs.environment.checks.checks
            for ref in check.evidence
            if ref.content_schema == "environment-selection/1"
        }
        if len(references) != 1:
            raise OwnershipConflict(
                "One original category environment selection required"
            )
        reference = next(iter(references))
        if (reference.visibility, reference.media_type) != (
            "private",
            "application/json",
        ):
            raise OwnershipConflict(
                "Private original category environment selection required"
            )
        raw = self.store.read(reference, control=control)
        require_complete_bytes(reference, raw)
        selected = EnvironmentSelection.model_validate_json(raw)
        if selected.model_dump_json().encode() != raw:
            raise OwnershipConflict("Canonical original category selection required")
        ref = selected.snapshot_ref
        if (ref.content_schema, ref.visibility, ref.media_type) != (
            "shopping-category-recovery/1",
            "private",
            "application/json",
        ):
            raise OwnershipConflict(
                "Private original category recovery snapshot required"
            )
        raw = self.store.read(ref, control=control)
        require_complete_bytes(ref, raw)
        saved = CategoryNavigationRecoverySnapshot.model_validate_json(raw)
        if saved.model_dump_json().encode() != raw:
            raise OwnershipConflict(
                "Canonical original category recovery snapshot required"
            )
        scope, request = inputs.prepared.scope, saved.request
        if (
            selected.scope != scope
            or selected.spec_ref != inputs.spec_ref
            or request.task != scope.task
            or (
                request.operation.run_id,
                request.operation.owner_id,
                request.operation.attempt_id,
            )
            != (scope.owner.run_id, scope.owner.owner_id, scope.attempt_id)
            or request.binding_ref != inputs.preparation.task_binding_ref
            or request.operation.allocation_id
            != inputs.environment.allocation.allocation_id
            or request.operation.recovery_ref != inputs.prepared.recovery_ref
            or inputs.preparation.recovery_ref != inputs.prepared.recovery_ref
            or hashlib.sha256(saved.state.model_dump_json().encode()).hexdigest()
            != inputs.environment.measured_state_sha256
            or saved.contents is None
        ):
            raise OwnershipConflict(
                "Original same-scope category snapshot and full contents required"
            )
        saved.contents.require_snapshot(saved.state)
        return saved.contents, ref

    def compare(
        self,
        source: PublicContextInputs,
        candidate: BaselineInputs,
        control: OperationControl,
    ) -> StateChecks:
        source = PublicContextInputs.model_validate(source)
        candidate = BaselineInputs.model_validate(candidate)
        control.checkpoint()
        original = source.baseline_inputs
        scope, old = candidate.prepared.scope, original.prepared.scope
        if (
            candidate.spec != category_navigation_initial_spec(scope.task)
            or original.spec != candidate.spec
            or source.baseline.status != "ready"
            or source.reset.status != "safe"
            or source.baseline.scope != old
            or source.reset.scope != old
            or scope.owner != old.owner
            or scope.attempt_id == old.attempt_id
            or scope.task != old.task
            or source.context.task != candidate.public_task
        ):
            raise OwnershipConflict(
                "Qualified original category source and distinct same-owner candidate required"
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
                or inputs.preparation.checks.required != inputs.spec.preparation_checks
                or inputs.environment.checks.status != "pass"
                or inputs.preparation.checks.status != "pass"
                or inputs.initial.checks.status != "pass"
            ):
                raise OwnershipConflict(
                    "Complete original category initial measurements required"
                )
        left, left_ref = self.contents(original, control)
        right, right_ref = self.contents(candidate, control)
        equal = left.content_sha256 == right.content_sha256
        control.checkpoint()
        return StateChecks(
            required=candidate.spec.equivalence_checks,
            checks=(
                CheckResult(
                    name="shopping.initial.equivalence",
                    status="pass" if equal else "fail",
                    reason_code=(
                        "ORIGINAL_SHOPPING_CONTENTS_EQUAL"
                        if equal
                        else "ORIGINAL_SHOPPING_CONTENTS_DIFFER"
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
