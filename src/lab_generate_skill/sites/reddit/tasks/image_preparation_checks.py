"""Reconstruct original Reddit no-op preparation from full native private evidence."""

from lab_generate_skill.domain.preparation_record import PreparationInputs
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from ..state_reads import RedditStateReads
from .image_spec import NativeImageSpec
from .image_admission import task_input
from .image_recovery import ImageRecoverySnapshot, ImageObserved
from .image_policy import image_initial_spec, PREPARATION_CHECKS


class ImagePreparationChecks(RedditStateReads):
    def check(
        self, inputs: PreparationInputs, control: OperationControl
    ) -> StateChecks:
        inputs = PreparationInputs.model_validate(inputs)
        request = inputs.request
        spec = task_input(request)
        if inputs.spec != image_initial_spec(request.task):
            raise ValueError("Unsupported Reddit preparation coverage")
        if (
            inputs.recovery.restore_component_id,
            inputs.recovery.restore_component_version,
            inputs.recovery.baseline_ref,
        ) != ("reddit-native-image", "1", inputs.binding.baseline_ref):
            raise ValueError("Unsupported original native-image recovery")
        private = self.read(
            inputs.binding.private_spec_ref,
            "reddit-native-image/1",
            NativeImageSpec,
            control,
        )
        if private != spec or request.snapshot_ref is None:
            raise OwnershipConflict(
                "Reddit preparation changed bound private input/snapshot"
            )
        snapshot = self.read(
            request.snapshot_ref,
            "reddit-image-recovery/2",
            ImageRecoverySnapshot,
            control,
        )
        snapshot.check_request(request)
        context = snapshot.native_before.context
        if (
            context.token != inputs.environment.allocation
            or context.instance.files != snapshot.state.service.files
        ):
            raise OwnershipConflict(
                "native-image preparation changed original environment allocation"
            )
        observed = ImageObserved.model_validate_json(inputs.result.private_result)
        if (
            observed.model_dump_json() != inputs.result.private_result
            or observed.request != request
            or observed.snapshot != snapshot
        ):
            raise OwnershipConflict(
                "Original native-image preparation measurement changed"
            )
        before = self.reference(snapshot.native_before, snapshot.request, control)
        snapshot.media_initialization.check_baseline(before.capture.native_media)
        current = self.capture(observed.native, request, control)
        if before.capture != current:
            raise OwnershipConflict(
                "native-image preparation changed complete original native state"
            )
        return self.checks(
            PREPARATION_CHECKS,
            (
                inputs.selection.request_ref,
                inputs.selection.result_ref,
                request.snapshot_ref,
                inputs.binding.private_spec_ref,
                snapshot.native_before.payload_ref,
                observed.native.payload_ref,
            ),
            "ORIGINAL_REDDIT_NATIVE_PREPARED",
        )
