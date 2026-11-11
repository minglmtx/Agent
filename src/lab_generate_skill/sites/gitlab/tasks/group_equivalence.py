"""Compare measured complete Group contents across distinct original attempts.

Physical paths/PIDs are not content. Full tree inventory, pinned image and the
original selected SQL/project-copy facts must all match; differing bytes fail.
This readonly comparison grants no source, claim, Actor or training permission.
"""

from dataclasses import dataclass
import hashlib
from lab_generate_skill.domain.baseline import BaselineInputs
from lab_generate_skill.domain.public_context import PublicContextInputs
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.evaluation import CheckResult
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from ..snapshot import GitlabInventory
from .group_capture import GroupCapturedFacts, same_group_state
from .group_reads import GroupStateReads
from .group_recovery import GroupRecoverySnapshot
from .group_policy import group_initial_spec


@dataclass(frozen=True)
class GroupInitialContents:
    image_sha256: str
    inventory: GitlabInventory
    native: GroupCapturedFacts
    snapshot_ref: EvidenceRef
    native_ref: EvidenceRef


class GroupInitialComparison:
    def __init__(self, reads: GroupStateReads) -> None:
        if not isinstance(reads, GroupStateReads):
            raise TypeError("Original complete Group state reader required")
        self.reads = reads

    def contents(
        self, inputs: BaselineInputs, control: OperationControl
    ) -> GroupInitialContents:
        references = {
            ref
            for checked in inputs.environment.checks.checks
            for ref in checked.evidence
            if ref.content_schema == "environment-selection/1"
        }
        if len(references) != 1:
            raise OwnershipConflict("One original Group environment selection required")
        selection = self.reads.read(
            next(iter(references)),
            "environment-selection/1",
            EnvironmentSelection,
            control,
        )
        saved = self.reads.read(
            selection.snapshot_ref,
            "gitlab-group-recovery/1",
            GroupRecoverySnapshot,
            control,
        )
        scope, request = inputs.prepared.scope, saved.request
        measured = hashlib.sha256(
            saved.state.model_dump_json().encode()
            + saved.native_before.payload_ref.sha256.encode()
        ).hexdigest()
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
            or measured != inputs.environment.measured_state_sha256
        ):
            raise OwnershipConflict(
                "Group comparison lost original snapshot/scope measurement"
            )
        native = self.reads.native(saved.native_before, request, control)
        return GroupInitialContents(
            saved.state.service.files.image.sha256,
            saved.state.inventory,
            native,
            selection.snapshot_ref,
            saved.native_before.payload_ref,
        )

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
        scope = candidate.prepared.scope
        if (
            candidate.spec != group_initial_spec(scope.task)
            or original.spec != candidate.spec
            or source.baseline.status != "ready"
            or source.reset.status != "safe"
            or source.baseline.scope != original.prepared.scope
            or source.reset.scope != original.prepared.scope
            or scope.owner != original.prepared.scope.owner
            or scope.attempt_id == original.prepared.scope.attempt_id
            or scope.task != original.prepared.scope.task
            or source.context.task != candidate.public_task
        ):
            raise OwnershipConflict(
                "Ready safely reset Group source and distinct same-owner task attempt required"
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
                or inputs.preparation.checks.required != inputs.spec.preparation_checks
                or inputs.initial.checks.required != inputs.spec.initial_checks
                or any(
                    checks.status != "pass"
                    for checks in (
                        inputs.environment.checks,
                        inputs.preparation.checks,
                        inputs.initial.checks,
                    )
                )
            ):
                raise OwnershipConflict(
                    "Complete original ready Group initial measurements required"
                )
        left, right = self.contents(original, control), self.contents(
            candidate, control
        )
        equal = (
            left.image_sha256 == right.image_sha256
            and left.inventory == right.inventory
            and same_group_state(left.native, right.native)
        )
        control.checkpoint()
        return StateChecks(
            required=candidate.spec.equivalence_checks,
            checks=(
                CheckResult(
                    name="gitlab.initial.equivalence",
                    status="pass" if equal else "fail",
                    reason_code=(
                        "ORIGINAL_GROUP_FULL_TREE_AND_NATIVE_EQUAL"
                        if equal
                        else "ORIGINAL_GROUP_CONTENTS_DIFFER"
                    ),
                    evidence=(
                        source.baseline_ref,
                        original.environment_ref,
                        original.initial_ref,
                        left.snapshot_ref,
                        left.native_ref,
                        candidate.environment_ref,
                        candidate.initial_ref,
                        right.snapshot_ref,
                        right.native_ref,
                    ),
                ),
            ),
        )
