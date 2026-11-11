"""Original navigation request/private/recovery/snapshot proof, without I/O."""

import hashlib
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from .navigation_admission import task_input
from .navigation_recovery import NavigationSnapshot
from .state_policy import map_initial_spec
from lab_generate_skill.ports.lifecycle import OperationControl


def require_navigation_native_request(
    configuration: SiteWorkerConfiguration,
    request: SiteTaskRequest,
    binding: TaskBinding,
    recovery: RecoveryPlan,
    environment: RecoveryPlan,
    snapshot: NavigationSnapshot | None,
) -> None:
    request.check_site(configuration)
    inputs = configuration.map_inputs
    if not isinstance(inputs, MapNavigationWorkerInputs):
        raise OwnershipConflict("Original selected navigation inputs required")
    private = task_input(request)
    if (
        request.task != inputs.scope.task
        or request.operation.attempt_id != inputs.scope.attempt_id
        or private.native_contract_ref.sha256 != inputs.native_contract_sha256
        or hashlib.sha256(request.private_input.encode()).hexdigest()
        != inputs.private_input_sha256
        or binding.identity != request.task
        or binding.private_spec_ref.sha256 != inputs.private_input_sha256
    ):
        raise OwnershipConflict(
            "Native navigation changed original selected source/input"
        )
    if (
        recovery.owner,
        recovery.attempt_id,
        recovery.baseline_ref,
        recovery.restore_component_id,
        recovery.restore_component_version,
        recovery.state_coverage,
    ) != (
        inputs.scope.owner,
        inputs.scope.attempt_id,
        environment.baseline_ref,
        "map-native-navigation",
        "1",
        map_initial_spec(
            request.task, private.native_contract_ref.sha256
        ).task_reset_checks,
    ) or environment.owner != inputs.scope.owner:
        raise OwnershipConflict("Native navigation changed original full recovery")
    if request.action != "snapshot" and (
        snapshot is None
        or snapshot.native.plan.token != configuration.token
        or snapshot.native.plan.scope != inputs.scope
    ):
        raise OwnershipConflict(
            "Original native navigation snapshot allocation required"
        )


class NavigationNativeRequestChecks:
    def verify_inputs(
        self,
        configuration: SiteWorkerConfiguration,
        request: SiteTaskRequest,
        binding: TaskBinding,
        recovery: RecoveryPlan,
        environment: RecoveryPlan,
        snapshot_bytes: bytes | None,
        snapshot_request: SiteTaskRequest | None,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        snapshot: NavigationSnapshot | None = None
        if request.action != "snapshot":
            if snapshot_bytes is None or snapshot_request is None:
                raise OwnershipConflict(
                    "Original complete navigation snapshot bytes required"
                )
            snapshot = NavigationSnapshot.model_validate_json(snapshot_bytes)
            if snapshot.request != snapshot_request:
                raise OwnershipConflict(
                    "Native snapshot came from another original request"
                )
        require_navigation_native_request(
            configuration, request, binding, recovery, environment, snapshot
        )
        control.checkpoint()
