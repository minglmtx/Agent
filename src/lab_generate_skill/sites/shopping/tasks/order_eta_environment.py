"""Original Shopping environment records; provenance authority remains mandatory."""

import hashlib
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.domain.state_checks import InitialStateSpec
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.lifecycle import OperationContext, RecoveryPlan
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from ..state_reads import ShoppingStateReads
from .order_eta_native import SHOPPING_IMAGE_SHA
from .order_eta_admission import task_input
from .order_eta_spec import OrderEtaSpec
from .order_eta_recovery import OrderEtaRecoverySnapshot
from .order_eta_policy import (
    order_eta_initial_spec,
    ENVIRONMENT_CHECKS,
    ENVIRONMENT_RESET_CHECKS,
)
from lab_generate_skill.domain.identity import TaskIdentity
from .state_codec import ShoppingTaskStateCodec, Snapshot


class OrderEtaEnvironmentChecks(ShoppingStateReads):
    def task_codec(self, task: TaskIdentity) -> ShoppingTaskStateCodec:
        return ShoppingTaskStateCodec(task, "recorded_order_eta")

    def _environment(
        self, selection: EnvironmentSelection, control: OperationControl
    ) -> tuple[InitialStateSpec, SiteResourceSpec, Snapshot]:
        selection = EnvironmentSelection.model_validate(selection)
        codec = self.task_codec(selection.scope.task)
        spec = self.read(
            selection.spec_ref, "initial-state-spec/1", InitialStateSpec, control
        )
        if spec != codec.policy:
            raise ValueError("Unsupported or incomplete Shopping initial-state policy")
        site = self.read(
            selection.site_spec_ref, "site-resource-spec/1", SiteResourceSpec, control
        )
        started = self.read(
            selection.site_started_ref,
            "site-resource-started/1",
            SiteResourceStarted,
            control,
        )
        snapshot = self.read(
            selection.snapshot_ref,
            codec.snapshot_schema,
            codec.snapshot_type,
            control,
        )
        request, config, scope = snapshot.request, site.configuration, selection.scope
        request.check_site(config)
        private_input = codec.private(request)
        if (site.token.owner, request.task, request.operation.attempt_id) != (
            scope.owner,
            scope.task,
            scope.attempt_id,
        ):
            raise OwnershipConflict("Shopping environment changed original task/scope")
        binding = self.read(request.binding_ref, "task-binding/1", TaskBinding, control)
        if (binding.identity, binding.baseline_ref) != (scope.task, selection.spec_ref):
            raise OwnershipConflict(
                "Shopping environment changed original task binding/spec"
            )
        private = self.read(
            binding.private_spec_ref,
            codec.private_schema,
            codec.private_type,
            control,
        )
        if private != private_input:
            raise OwnershipConflict(
                "Shopping snapshot changed original bound private specification"
            )
        service = snapshot.state.service
        ports = service.ports
        if (
            config.site_id != "shopping"
            or service.files != config.files
            or service.apptainer != config.apptainer
            or config.files.image.sha256 != SHOPPING_IMAGE_SHA
            or started.instance.files != config.files
            or service.endpoint != started.instance.endpoint
            or (ports.web, ports.database, ports.redis, ports.search, ports.transport)
            != started.instance.ports
        ):
            raise OwnershipConflict(
                "Shopping environment changed original instance/image/ports"
            )
        installed = started.ready.worker.installed_sources
        if (installed.release_id, installed.manifest_sha256, installed.executable) != (
            config.installation.manifest.release_id,
            config.installation.manifest_ref.sha256,
            config.installation.python_executable,
        ):
            raise OwnershipConflict("Shopping environment changed installed release")
        worker = started.ready.worker.owner_guard.worker
        for stopped in snapshot.state.original_stop.namespaces:
            for process in (stopped.original.launcher, stopped.original.init):
                if (process.node_id, process.boot_id) != (
                    worker.node_id,
                    worker.boot_id,
                ) or process.start_ticks < worker.start_ticks:
                    raise OwnershipConflict(
                        "Shopping snapshot changed original worker host/boot"
                    )
        recovery = self.read(
            site.token.recovery_ref, "recovery-plan/1", RecoveryPlan, control
        )
        if (
            recovery.owner,
            recovery.attempt_id,
            recovery.baseline_ref,
            recovery.restore_component_id,
            recovery.restore_component_version,
            recovery.state_coverage,
        ) != (
            scope.owner,
            None,
            selection.spec_ref,
            "shopping-services",
            "1",
            ENVIRONMENT_RESET_CHECKS,
        ):
            raise ValueError(
                "Shopping environment recovery omits original resumed services"
            )
        return spec, site, snapshot

    def environment(
        self,
        selection: EnvironmentSelection,
        reference: EvidenceRef,
        operation: OperationContext,
        control: OperationControl,
    ) -> EnvironmentBaseline:
        spec, site, snapshot = self._environment(selection, control)
        if operation.recovery_ref != site.token.recovery_ref:
            raise OwnershipConflict("Shopping environment changed original recovery")
        return EnvironmentBaseline(
            scope=selection.scope,
            operation=operation,
            allocation=site.token,
            spec_ref=selection.spec_ref,
            checks=self.checks(
                ENVIRONMENT_CHECKS,
                (
                    reference,
                    selection.site_spec_ref,
                    selection.site_started_ref,
                    selection.snapshot_ref,
                ),
                "ORIGINAL_SHOPPING_ENVIRONMENT",
            ),
            measured_state_sha256=hashlib.sha256(
                snapshot.state.model_dump_json().encode()
            ).hexdigest(),
        )
