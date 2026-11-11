"""Recompute selected product preparation from original immutable facts.

No environment approval, model observation or side effects. Provenance and
writer/claim authorization are mandatory external authority responsibilities.
"""

from lab_generate_skill.domain.preparation_record import PreparationInputs
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.evaluation import CheckResult
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from .product_execution import ProductExecutionInput
from .product_description_spec import ProductDescriptionSpec
from .product_seed_contract import ProductSeedScenario, ProductState
from .product_seed_validation import validate_product_initial_state
from .product_recovery_contract import ProductRecoverySnapshot

PRODUCT_PREPARATION_CHECKS = (
    "admin.product.initial_fixture",
    "admin.product.original_snapshot",
)


class ProductPreparationChecks:
    def __init__(self, store: EvidenceReader) -> None:
        self.store = store

    def check(
        self, inputs: PreparationInputs, control: OperationControl
    ) -> StateChecks:
        inputs = PreparationInputs.model_validate(inputs)
        control.checkpoint()
        if inputs.spec.preparation_checks != PRODUCT_PREPARATION_CHECKS:
            raise ValueError("Unsupported product preparation coverage")
        request = inputs.request
        data = ProductExecutionInput.model_validate_json(request.private_input)
        if (
            data.model_dump_json() != request.private_input
            or data.spec.task != request.task
        ):
            raise OwnershipConflict("Product preparation changed canonical task input")
        if (
            inputs.recovery.restore_component_id,
            inputs.recovery.restore_component_version,
        ) != ("admin-product", "3"):
            raise ValueError("Unsupported product recovery component")
        if (
            inputs.binding.private_spec_ref.content_schema
            != "shopping-admin-product-description/1"
            or request.snapshot_ref is None
            or request.snapshot_ref.content_schema != "admin-product-recovery/2"
        ):
            raise ValueError("Unsupported product source schema")
        private = ProductDescriptionSpec.model_validate_json(
            self.store.read(inputs.binding.private_spec_ref, control=control)
        )
        seed = ProductSeedScenario.model_validate_json(
            self.store.read(data.seed.reference, control=control)
        )
        if private != data.spec or seed != data.seed.scenario:
            raise OwnershipConflict(
                "Product input differs from actual spec or seed bytes"
            )
        control.checkpoint()
        assert request.snapshot_ref is not None
        snapshot = ProductRecoverySnapshot.model_validate_json(
            self.store.read(request.snapshot_ref, control=control)
        )
        if (
            snapshot.product.product_id != data.spec.product_id
            or snapshot.state.plan.service.layout.instance_id
            != inputs.environment.allocation.expected_resource_id
        ):
            raise OwnershipConflict(
                "Snapshot product or instance differs from original environment"
            )
        old = snapshot.request
        if (
            old.task,
            old.binding_ref,
            old.private_input,
            old.operation.run_id,
            old.operation.owner_id,
            old.operation.attempt_id,
            old.operation.allocation_id,
            old.operation.recovery_ref,
        ) != (
            request.task,
            request.binding_ref,
            request.private_input,
            request.operation.run_id,
            request.operation.owner_id,
            request.operation.attempt_id,
            request.operation.allocation_id,
            request.operation.recovery_ref,
        ):
            raise OwnershipConflict("Preparation replaced original pre-effect snapshot")
        state = ProductState.model_validate_json(inputs.result.private_result)
        if state.model_dump_json() != inputs.result.private_result:
            raise ValueError("Noncanonical product measurement")
        validate_product_initial_state(data.spec, data.seed, state)
        control.checkpoint()
        return StateChecks(
            required=PRODUCT_PREPARATION_CHECKS,
            checks=(
                CheckResult(
                    name=PRODUCT_PREPARATION_CHECKS[0],
                    status="pass",
                    reason_code="DECLARED_FIXTURE_MEASURED",
                    evidence=(
                        inputs.selection.request_ref,
                        inputs.selection.result_ref,
                        inputs.binding.private_spec_ref,
                        data.seed.reference,
                    ),
                ),
                CheckResult(
                    name=PRODUCT_PREPARATION_CHECKS[1],
                    status="pass",
                    reason_code="ORIGINAL_SNAPSHOT_RETAINED",
                    evidence=(request.snapshot_ref, inputs.selection.request_ref),
                ),
            ),
        )
