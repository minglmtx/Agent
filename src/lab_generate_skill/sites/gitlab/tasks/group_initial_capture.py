"""Group's original native before-capture on the frozen initial-check lineage."""

import hashlib
from collections.abc import Callable
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.site_capture import SiteCaptureIntent, SiteCaptureRequest
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.domain.task_initialization import TaskInitializationPlan
from lab_generate_skill.domain.task_preparation import SiteTaskPrepared
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from ..evidence_schema import GitlabSiteCapture
from .group_capture import GroupCapturedFacts, same_group_state
from .group_environment import GroupEnvironmentChecks
from .group_request import task_input
from .group_source_initial import CapturedGroupInitialChecks
from .group_spec import GroupSpec
from .group_recovery import GroupObserved


def group_initial_capture_request(
    declaration: TaskInitializationPlan, prepared: SiteTaskRequest
) -> SiteCaptureRequest:
    declaration = TaskInitializationPlan.model_validate(declaration)
    prepared = SiteTaskRequest.model_validate(prepared)
    scope = declaration.scope
    private = task_input(prepared)
    if (
        prepared.action != "prepare"
        or prepared.snapshot_ref is None
        or private.task != scope.task
        or (
            prepared.operation.run_id,
            prepared.operation.owner_id,
            prepared.operation.attempt_id,
        )
        != (scope.owner.run_id, scope.owner.owner_id, scope.attempt_id)
        or prepared.operation.mode != "execute"
    ):
        raise OwnershipConflict("Original Group prepared attempt required")
    operation = prepared.operation.model_copy(
        update={
            "operation_id": declaration.initial_operation.operation_id
            + ".native-before",
            "parent_operation_id": declaration.capture_operation.operation_id,
            "deadline": min(
                prepared.operation.deadline, declaration.initial_operation.deadline
            ),
            "cancellation_ref": declaration.initial_operation.cancellation_ref,
        }
    )
    return SiteCaptureRequest(
        inspection=prepared.model_copy(
            update={"action": "inspect", "operation": operation}
        ),
        collector_id="gitlab-group-creation",
        collector_version="1",
    )


class GroupTaskInitialChecks:
    """Recheck native bytes and keep both captures in the original baseline."""

    def __init__(
        self,
        evidence: EvidenceReader,
        declaration: TaskInitializationPlan,
        page_intent: EvidenceRef,
        page_result: EvidenceRef,
        before: GitlabSiteCapture,
        native_loader: Callable[[bytes, GroupSpec], GroupCapturedFacts],
    ) -> None:
        self.evidence = evidence
        self.declaration = TaskInitializationPlan.model_validate(declaration)
        self.page_intent, self.page_result = page_intent, page_result
        self.before = GitlabSiteCapture.model_validate(before)
        self.page = CapturedGroupInitialChecks(evidence, page_intent, page_result)
        self.reads = GroupEnvironmentChecks(evidence, native_loader)

    def check(
        self, inputs: InitialObservationInputs, control: OperationControl
    ) -> StateChecks:
        checks = self.page.check(inputs, control)
        d, reads = self.declaration, self.reads
        original = reads.read(
            d.prepared_result_ref, "site-task-prepared/2", SiteTaskPrepared, control
        )
        request = reads.read(
            original.publication.selection.request_ref,
            "site-task-request/2",
            SiteTaskRequest,
            control,
        )
        environment = reads.read(
            original.environment_selection_ref,
            "environment-selection/1",
            EnvironmentSelection,
            control,
        )
        _, site, snapshot = reads._environment(environment, control)
        if (
            d.scope != inputs.prepared.scope
            or original.scope != d.scope
            or original.publication != inputs.selection.preparation
            or d.browser_spec_ref != inputs.selection.browser_spec_ref
            or request.binding_ref != inputs.prepared.task_binding_ref
            or request.snapshot_ref != environment.snapshot_ref
            or environment.scope != d.scope
            or environment.spec_ref != inputs.prepared.spec_ref
        ):
            raise OwnershipConflict(
                "Group native initial capture changed prepared lineage"
            )
        expected = group_initial_capture_request(d, request)
        intent = reads.read(
            self.before.intent_ref, "site-capture-intent/2", SiteCaptureIntent, control
        )
        returned = reads.read(
            self.before.result_ref, "site-task-result/1", SiteTaskResult, control
        )
        if (
            intent.request != expected
            or intent.configuration_sha256
            != hashlib.sha256(site.configuration.model_dump_json().encode()).hexdigest()
            or returned.request_sha256 != expected.digest
        ):
            raise EvidenceIntegrityError(
                "Group native initial capture lost exact original intent"
            )
        observed = GroupObserved.model_validate_json(returned.private_result)
        if (
            observed.model_dump_json() != returned.private_result
            or observed.request != expected.inspection
            or observed.snapshot != snapshot
            or observed.native.context != snapshot.native_before.context
        ):
            raise EvidenceIntegrityError(
                "Group native initial capture changed original snapshot/worker"
            )
        before = reads.native(snapshot.native_before, snapshot.request, control)
        current = reads.native(observed.native, expected.inspection, control)
        if not same_group_state(before, current):
            raise EvidenceIntegrityError(
                "Group changed original native state before Actor"
            )
        refs = (
            self.page_intent,
            self.page_result,
            self.before.intent_ref,
            self.before.result_ref,
        )
        control.checkpoint()
        return StateChecks(
            required=checks.required,
            checks=tuple(
                item.model_copy(
                    update={"evidence": tuple(dict.fromkeys((*item.evidence, *refs)))}
                )
                for item in checks.checks
            ),
        )
