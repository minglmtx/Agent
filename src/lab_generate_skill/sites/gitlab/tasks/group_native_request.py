"""Complete Group native input/recovery/snapshot rules, never a dispatch grant."""

import hashlib
from lab_generate_skill.domain.native_private_json import GITLAB_GROUP_PRIVATE_JSON
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from .group_request import task_input
from .group_policy import group_initial_spec
from .group_recovery import GroupRecoverySnapshot
from .native_snapshot import same_native_snapshot
from .group_worker_inputs import verify_group_worker_inputs


class GroupNativeRequestChecks:
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
        request, binding = SiteTaskRequest.model_validate(
            request
        ), TaskBinding.model_validate(binding)
        recovery, environment = RecoveryPlan.model_validate(
            recovery
        ), RecoveryPlan.model_validate(environment)
        control.checkpoint()
        request.check_site(configuration)
        verify_group_worker_inputs(configuration, request)
        private = task_input(request)
        raw = private.model_dump_json().encode()
        policy = group_initial_spec(request.task)
        if (
            configuration.site_id != "gitlab"
            or configuration.private_evidence is None
            or configuration.private_evidence.profile != GITLAB_GROUP_PRIVATE_JSON
            or request.action not in ("snapshot", "prepare", "restore")
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
            != ("gitlab-group-creation", "1", policy.task_reset_checks)
            or (
                environment.attempt_id,
                environment.restore_component_id,
                environment.restore_component_version,
                environment.state_coverage,
            )
            != (None, "gitlab-services", "1", policy.environment_reset_checks)
        ):
            raise OwnershipConflict(
                "Group native request changed original binding/full recovery"
            )
        if request.action == "snapshot":
            if snapshot_bytes is not None or snapshot_request is not None:
                raise OwnershipConflict("Original Group snapshot cannot be replaced")
        else:
            if snapshot_bytes is None or snapshot_request is None:
                raise OwnershipConflict("Original complete Group snapshot required")
            saved = GroupRecoverySnapshot.model_validate_json(snapshot_bytes)
            if (
                saved.model_dump_json().encode() != snapshot_bytes
                or saved.request != snapshot_request
                or saved.state.service.files != configuration.files
                or saved.state.service.apptainer != configuration.apptainer
                or saved.native_before.context.token != configuration.token
                or saved.native_before.context.configuration_sha256
                != hashlib.sha256(configuration.model_dump_json().encode()).hexdigest()
            ):
                raise OwnershipConflict(
                    "Group native request changed original snapshot/resource"
                )
            same_native_snapshot(
                request,
                saved.request,
                snapshot_bytes,
                saved.schema_version,
                None,
                "Group",
            )
            if request.snapshot_ref is None or (
                request.snapshot_ref.visibility,
                request.snapshot_ref.media_type,
            ) != ("private", "application/json"):
                raise OwnershipConflict(
                    "Original private complete Group snapshot reference required"
                )
        control.checkpoint()
