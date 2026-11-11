"""Navigation-specific native input/recovery proof for existing task authorities.

No I/O, permissions or once state live here. The original source qualification
or task producer must separately prove its live owner, acquired resource and
pending immutable intent, and closed browser before a restore dispatch.
"""

import hashlib
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from ..instance_contract import AdminInstancePlan
from ..artifact_contract import ARTIFACT_PATHS
from .navigation_recovery_contract import (
    NavigationExecutionInput,
    NavigationRecoverySnapshot,
)
from .navigation_state_policy import navigation_initial_state_spec


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
        configuration = SiteWorkerConfiguration.model_validate(configuration)
        request = SiteTaskRequest.model_validate(request)
        binding = TaskBinding.model_validate(binding)
        recovery = RecoveryPlan.model_validate(recovery)
        environment = RecoveryPlan.model_validate(environment)
        control.checkpoint()
        request.check_site(configuration)
        inputs = NavigationExecutionInput.model_validate_json(request.private_input)
        private = inputs.spec
        raw = private.model_dump_json().encode()
        policy = navigation_initial_state_spec(request.task)
        declared = configuration.admin_navigation_inputs
        if (
            declared is None
            or configuration.schema_version != "site-worker-configuration/7"
        ):
            raise OwnershipConflict(
                "Explicit original version7 Admin navigation resource required"
            )
        if (
            configuration.site_id != "shopping_admin"
            or request.action not in ("snapshot", "prepare", "restore")
            or inputs.model_dump_json() != request.private_input
            or (declared.scope.owner, declared.scope.task, declared.scope.attempt_id)
            != (configuration.token.owner, request.task, request.operation.attempt_id)
            or declared.native_contract_sha256 != private.native_contract_ref.sha256
            or declared.private_input_sha256
            != hashlib.sha256(request.private_input.encode()).hexdigest()
            or private.task != request.task
            or binding.identity != request.task
            or (
                binding.private_spec_ref.content_schema,
                binding.private_spec_ref.visibility,
                binding.private_spec_ref.media_type,
                binding.private_spec_ref.sha256,
                binding.private_spec_ref.size_bytes,
            )
            != (
                private.schema_version,
                "private",
                "application/json",
                hashlib.sha256(raw).hexdigest(),
                len(raw),
            )
            or binding.baseline_ref != recovery.baseline_ref
            or environment.baseline_ref != recovery.baseline_ref
            or recovery.owner != configuration.token.owner
            or environment.owner != configuration.token.owner
            or recovery.attempt_id != request.operation.attempt_id
            or (
                recovery.restore_component_id,
                recovery.restore_component_version,
                recovery.state_coverage,
            )
            != ("admin-navigation", "1", policy.task_reset_checks)
            or (
                environment.attempt_id,
                environment.restore_component_id,
                environment.restore_component_version,
                environment.state_coverage,
            )
            != (None, "admin-frontend", "1", policy.environment_reset_checks)
        ):
            raise OwnershipConflict(
                "Native navigation changed original source/input/full recovery"
            )
        if request.action == "snapshot":
            if snapshot_bytes is not None or snapshot_request is not None:
                raise OwnershipConflict(
                    "Original navigation snapshot cannot be replaced"
                )
        else:
            if snapshot_bytes is None or snapshot_request is None:
                raise OwnershipConflict(
                    "Original complete navigation snapshot required"
                )
            saved = NavigationRecoverySnapshot.model_validate_json(snapshot_bytes)
            original = saved.request
            reference = request.snapshot_ref
            if (
                saved.model_dump_json().encode() != snapshot_bytes
                or original != snapshot_request
                or (original.task, original.binding_ref, original.private_input)
                != (request.task, request.binding_ref, request.private_input)
                or any(
                    getattr(original.operation, name)
                    != getattr(request.operation, name)
                    for name in (
                        "run_id",
                        "owner_id",
                        "attempt_id",
                        "allocation_id",
                        "recovery_ref",
                    )
                )
                or reference is None
                or (
                    reference.content_schema,
                    reference.sha256,
                    reference.size_bytes,
                    reference.visibility,
                    reference.media_type,
                )
                != (
                    saved.schema_version,
                    hashlib.sha256(snapshot_bytes).hexdigest(),
                    len(snapshot_bytes),
                    "private",
                    "application/json",
                )
                or saved.state.plan.service.layout
                != AdminInstancePlan(
                    files=configuration.files, apptainer=configuration.apptainer
                ).layout
                or saved.state.plan.artifacts.paths != tuple(sorted(ARTIFACT_PATHS))
                or saved.contents is None
                or saved.state.plan.service.admin_url != declared.origin.endpoint
            ):
                raise OwnershipConflict(
                    "Native navigation changed original measured snapshot/resource"
                )
            saved.contents.require_snapshot(saved.state)
        control.checkpoint()
