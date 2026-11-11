"""Original three-service/full-native environment semantics, without launch rights."""

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
from ..state_reads import RedditStateReads
from ..service_contract import IMAGE_SHA256
from .image_spec import NativeImageSpec
from .image_admission import task_input
from .image_recovery import ImageRecoverySnapshot
from .image_policy import (
    image_initial_spec,
    ENVIRONMENT_CHECKS,
    ENVIRONMENT_RESET_CHECKS,
)


class ImageEnvironmentChecks(RedditStateReads):
    def _environment(
        self, selection: EnvironmentSelection, control: OperationControl
    ) -> tuple[InitialStateSpec, SiteResourceSpec, ImageRecoverySnapshot]:
        selection = EnvironmentSelection.model_validate(selection)
        spec = self.read(
            selection.spec_ref, "initial-state-spec/1", InitialStateSpec, control
        )
        if spec != image_initial_spec(selection.scope.task):
            raise ValueError("Unsupported or incomplete Reddit initial-state coverage")
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
            "reddit-image-recovery/2",
            ImageRecoverySnapshot,
            control,
        )
        request, config, scope = snapshot.request, site.configuration, selection.scope
        request.check_site(config)
        private = task_input(request)
        if (site.token.owner, request.task, request.operation.attempt_id) != (
            scope.owner,
            scope.task,
            scope.attempt_id,
        ):
            raise OwnershipConflict("Reddit environment changed original scope")
        binding = self.read(request.binding_ref, "task-binding/1", TaskBinding, control)
        bound = self.read(
            binding.private_spec_ref, "reddit-native-image/1", NativeImageSpec, control
        )
        if (binding.identity, binding.baseline_ref, bound) != (
            scope.task,
            selection.spec_ref,
            private,
        ):
            raise OwnershipConflict(
                "Reddit environment changed original private binding/spec"
            )
        service = snapshot.state.service
        context = snapshot.native_before.context
        if (
            config.site_id != "reddit"
            or service.files != config.files
            or service.apptainer != config.apptainer
            or config.files.image.sha256 != IMAGE_SHA256
            or started.instance.files != config.files
            or service.endpoint != started.instance.endpoint
            or (service.ports.web, service.ports.database) != started.instance.ports
            or context.configuration_sha256
            != hashlib.sha256(config.model_dump_json().encode()).hexdigest()
            or context.token != site.token
            or context.instance != started.instance
            or context.owner_guard != started.ready.worker.owner_guard
            or context.owner_guard.controller != site.slurm.parent.writer
        ):
            raise OwnershipConflict(
                "Reddit environment lost original image/site/worker/ports"
            )
        installed = started.ready.worker.installed_sources
        if (installed.release_id, installed.manifest_sha256, installed.executable) != (
            config.installation.manifest.release_id,
            config.installation.manifest_ref.sha256,
            config.installation.python_executable,
        ):
            raise OwnershipConflict(
                "Reddit environment changed original installed release"
            )
        worker = context.owner_guard.worker
        for stopped in snapshot.state.original_stop.namespaces:
            for process in (stopped.original.launcher, stopped.original.init):
                if (process.node_id, process.boot_id) != (
                    worker.node_id,
                    worker.boot_id,
                ) or process.start_ticks < worker.start_ticks:
                    raise OwnershipConflict(
                        "Reddit snapshot changed original worker host/boot/order"
                    )
        reference = self.reference(snapshot.native_before, request, control)
        snapshot.media_initialization.check_baseline(reference.capture.native_media)
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
            "reddit-services",
            "1",
            ENVIRONMENT_RESET_CHECKS,
        ):
            raise ValueError(
                "Reddit environment recovery omits original three-service resume"
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
            raise OwnershipConflict("Reddit environment changed original recovery")
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
                    snapshot.native_before.payload_ref,
                ),
                "ORIGINAL_REDDIT_ENVIRONMENT",
            ),
            measured_state_sha256=hashlib.sha256(
                snapshot.state.model_dump_json().encode()
                + snapshot.native_before.payload_ref.sha256.encode()
            ).hexdigest(),
        )
