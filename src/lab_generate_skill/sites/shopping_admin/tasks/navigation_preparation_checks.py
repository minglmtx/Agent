"""Recompute navigation preparation from exact original native snapshot facts.

This verifies a no-task-mutation preparation declaration, not a live initial
view, current database equality, source permission or complete Reset receipt.
"""

import hashlib
from urllib.parse import urlsplit
from lab_generate_skill.domain.preparation_record import PreparationInputs
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.evaluation import CheckResult
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from ..preparation_bodies import NavigationPreparationBodies
from .product_state_checks import ProductStateChecks
from .navigation_spec import AdminNavigationSpec
from .navigation_recovery_contract import (
    NavigationExecutionInput,
    NavigationRecoverySnapshot,
    NavigationPrepared,
)

NAVIGATION_PREPARATION_CHECKS = (
    "admin.navigation.preparation.declaration",
    "admin.navigation.original_snapshot",
)


class NavigationPreparationChecks:
    def __init__(self, store: EvidenceReader) -> None:
        # Reuse the existing canonical private JSON reader only. Product state
        # policy/absence or environment/Reset algorithms are never dispatched.
        self.records = ProductStateChecks(store)

    def check_with_bodies(
        self,
        inputs: PreparationInputs,
        private_spec: bytes | None,
        snapshot: bytes | None,
        control: OperationControl,
    ) -> StateChecks:
        inputs = PreparationInputs.model_validate(inputs)
        control.checkpoint()
        reader = NavigationPreparationBodies(
            self.records.store, inputs, private_spec, snapshot
        )
        return NavigationPreparationChecks(reader).check(inputs, control)

    def check(
        self, inputs: PreparationInputs, control: OperationControl
    ) -> StateChecks:
        inputs = PreparationInputs.model_validate(inputs)
        control.checkpoint()
        if inputs.spec.preparation_checks != NAVIGATION_PREPARATION_CHECKS:
            raise ValueError("Unsupported navigation preparation coverage")
        if (
            inputs.recovery.restore_component_id,
            inputs.recovery.restore_component_version,
        ) != ("admin-navigation", "1"):
            raise ValueError("Unsupported navigation recovery component")
        request = inputs.request
        data = NavigationExecutionInput.model_validate_json(request.private_input)
        private = self.records.read(
            inputs.binding.private_spec_ref,
            "shopping-admin-page-navigation/1",
            AdminNavigationSpec,
            control,
        )
        if (
            data.model_dump_json() != request.private_input
            or private != data.spec
            or private.task != request.task
        ):
            raise OwnershipConflict(
                "Navigation preparation changed original canonical task data"
            )
        if urlsplit(inputs.public_task.start_url).path != "/admin" + private.start_path:
            raise OwnershipConflict(
                "Navigation preparation changed original declared start"
            )
        if request.snapshot_ref is None:
            raise OwnershipConflict("Navigation preparation needs original snapshot")
        snapshot = self.records.read(
            request.snapshot_ref,
            "admin-navigation-recovery/1",
            NavigationRecoverySnapshot,
            control,
        )
        old = snapshot.request
        for name in ("task", "binding_ref", "private_input"):
            if getattr(old, name) != getattr(request, name):
                raise OwnershipConflict(
                    "Navigation preparation changed original snapshot task"
                )
        for name in (
            "run_id",
            "owner_id",
            "attempt_id",
            "allocation_id",
            "recovery_ref",
        ):
            if getattr(old.operation, name) != getattr(request.operation, name):
                raise OwnershipConflict(
                    "Navigation preparation changed original snapshot scope"
                )
        if (
            snapshot.state.plan.service.layout.instance_id
            != inputs.environment.allocation.expected_resource_id
        ):
            raise OwnershipConflict(
                "Navigation snapshot belongs to another original instance"
            )
        prepared = NavigationPrepared.model_validate_json(inputs.result.private_result)
        if prepared.model_dump_json() != inputs.result.private_result or (
            prepared.task,
            prepared.snapshot_ref,
            prepared.private_spec_sha256,
            prepared.state_snapshot_sha256,
            prepared.initialization,
            prepared.start_path,
        ) != (
            request.task,
            request.snapshot_ref,
            hashlib.sha256(private.model_dump_json().encode()).hexdigest(),
            snapshot.state.digest,
            private.initialization,
            private.start_path,
        ):
            raise OwnershipConflict(
                "Navigation preparation changed original snapshot/start declaration"
            )
        control.checkpoint()
        return StateChecks(
            required=NAVIGATION_PREPARATION_CHECKS,
            checks=(
                CheckResult(
                    name=NAVIGATION_PREPARATION_CHECKS[0],
                    status="pass",
                    reason_code="ORIGINAL_NAVIGATION_PREPARATION_DECLARATION",
                    evidence=(
                        inputs.selection.request_ref,
                        inputs.selection.result_ref,
                        inputs.binding.private_spec_ref,
                    ),
                ),
                CheckResult(
                    name=NAVIGATION_PREPARATION_CHECKS[1],
                    status="pass",
                    reason_code="ORIGINAL_NAVIGATION_SNAPSHOT_RETAINED",
                    evidence=(request.snapshot_ref, inputs.selection.request_ref),
                ),
            ),
        )
