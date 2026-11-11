"""Category native input/recovery proof; live intent and rights stay original."""

import hashlib
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from .navigation_admission import task_input, same_snapshot
from .navigation_policy import category_navigation_initial_spec
from .navigation_recovery import CategoryNavigationRecoverySnapshot
from .order_eta_native import SHOPPING_IMAGE_SHA


class CategoryNavigationNativeRequestChecks:
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
        data = task_input(request)
        spec, token = data.spec, configuration.token
        policy = category_navigation_initial_spec(request.task)
        raw = spec.model_dump_json().encode()
        if configuration.schema_version == "site-worker-configuration/9":
            selected = configuration.shopping_category_inputs
            if (
                selected is None
                or selected.scope.owner != token.owner
                or selected.scope.task != request.task
                or selected.scope.attempt_id != request.operation.attempt_id
                or selected.native_contract_sha256 != spec.native_contract_ref.sha256
                or selected.private_input_sha256
                != hashlib.sha256(request.private_input.encode()).hexdigest()
            ):
                raise OwnershipConflict(
                    "Category native call changed version9 scope/input pins"
                )
        if (
            configuration.site_id != "shopping"
            or configuration.schema_version
            not in ("site-worker-configuration/6", "site-worker-configuration/9")
            or configuration.files.image.sha256 != SHOPPING_IMAGE_SHA
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
                spec.schema_version,
                "private",
                "application/json",
                hashlib.sha256(raw).hexdigest(),
                len(raw),
            )
            or binding.baseline_ref != recovery.baseline_ref
            or environment.baseline_ref != recovery.baseline_ref
            or recovery.owner != token.owner
            or environment.owner != token.owner
            or (
                recovery.attempt_id,
                recovery.restore_component_id,
                recovery.restore_component_version,
                recovery.state_coverage,
            )
            != (
                request.operation.attempt_id,
                "shopping-category-navigation",
                "1",
                policy.task_reset_checks,
            )
            or (
                environment.attempt_id,
                environment.restore_component_id,
                environment.restore_component_version,
                environment.state_coverage,
            )
            != (None, "shopping-services", "1", policy.environment_reset_checks)
        ):
            raise OwnershipConflict(
                "Category native call changed original input/resource/full recovery"
            )
        if request.action == "snapshot":
            if snapshot_bytes is not None or snapshot_request is not None:
                raise OwnershipConflict("Category snapshot cannot replace prior state")
        else:
            if type(snapshot_bytes) is not bytes or snapshot_request is None:
                raise OwnershipConflict("Complete original category snapshot required")
            saved = CategoryNavigationRecoverySnapshot.model_validate_json(
                snapshot_bytes
            )
            if (
                saved.model_dump_json().encode() != snapshot_bytes
                or saved.request != snapshot_request
                or saved.state.service.files != configuration.files
                or saved.state.service.apptainer != configuration.apptainer
            ):
                raise OwnershipConflict("Category snapshot changed original resource")
            same_snapshot(request, saved, request.snapshot_ref)
            selected = configuration.shopping_category_inputs
            if (
                selected is not None
                and saved.state.service.ports.web != selected.origin.web_port
            ):
                raise OwnershipConflict(
                    "Category snapshot changed declared original web port"
                )
        control.checkpoint()
