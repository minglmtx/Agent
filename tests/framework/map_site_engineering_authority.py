"""Exact fresh Map source intents; existing kernel/resource authority remains required."""

from datetime import datetime, timezone
import hashlib
from uuid import uuid4
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from lab_generate_skill.sites.map.tasks.overlay_policy import overlay_initial_spec
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.tasks.overlay_recovery import OverlaySnapshot
from lab_generate_skill.sites.map.tasks.state_codec import MapTaskStateCodec
from lab_generate_skill.sites.map.tasks.state_policy import map_initial_spec
from lab_generate_skill.sites.map.tasks.state_admission import snapshot_reference
from test_site_resource_installed import EngineeringAuthority


class MapEngineeringAuthority(EngineeringAuthority):
    def verify_task(
        self,
        config: SiteWorkerConfiguration,
        request: SiteTaskRequest,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        request.check_site(config)
        inputs = config.map_inputs
        if (
            config != self.case.spec.configuration
            or config.site_id != "map"
            or inputs is None
            or not self.before_native
            or request.operation.operation_id not in self.task_intents
        ):
            raise OwnershipConflict(
                "Original acquired Map instance and persisted task intent required"
            )
        if (
            request.task != inputs.scope.task
            or request.operation.attempt_id != inputs.scope.attempt_id
        ):
            raise OwnershipConflict("Map task changed original selected source/attempt")
        assert request.operation.recovery_ref is not None
        codec = MapTaskStateCodec(request.task)
        private = codec.private_type.model_validate_json(request.private_input)
        task_recovery = RecoveryPlan.model_validate_json(
            self.store.read(request.operation.recovery_ref, control=control)
        )
        environment = RecoveryPlan.model_validate_json(
            self.store.read(config.token.recovery_ref, control=control)
        )
        if (
            task_recovery.owner,
            task_recovery.attempt_id,
            task_recovery.baseline_ref,
            task_recovery.restore_component_id,
            task_recovery.restore_component_version,
            task_recovery.state_coverage,
        ) != (
            inputs.scope.owner,
            inputs.scope.attempt_id,
            environment.baseline_ref,
            codec.recovery_component,
            "1",
            map_initial_spec(
                inputs.scope.task, private.native_contract_ref.sha256
            ).task_reset_checks,
        ):
            raise OwnershipConflict(
                "Map task changed original complete recovery declaration"
            )
        raw = self.store.read(
            self.task_intents[request.operation.operation_id], control=control
        )
        if (
            raw != request.model_dump_json().encode()
            or request.private_input != self.task_input
            or hashlib.sha256(request.private_input.encode()).hexdigest()
            != inputs.private_input_sha256
        ):
            raise OwnershipConflict(
                "Original Map task intent or private source pin changed"
            )
        if request.action != "snapshot":
            if request.snapshot_ref is None:
                raise OwnershipConflict("Original complete Map snapshot required")
            raw_snapshot = self.store.read(request.snapshot_ref, control=control)
            snapshot = codec.snapshot_type.model_validate_json(raw_snapshot)
            if (
                snapshot.native.plan.token != config.token
                or snapshot.native.plan.scope != inputs.scope
            ):
                raise OwnershipConflict(
                    "Map task changed original snapshot allocation/scope"
                )
            snapshot_reference(
                request,
                snapshot.request,
                raw_snapshot,
                request.snapshot_ref,
                schema_version=codec.snapshot_schema,
            )
        read = self.case.op.cleanup(
            "map-task-ledger-" + uuid4().hex,
            now=datetime.now(timezone.utc),
            seconds=10,
        )
        if self.case.journal.read(config.token, read).state != "acquired":
            raise OwnershipConflict("Original Map site resource is not acquired")
        control.checkpoint()
