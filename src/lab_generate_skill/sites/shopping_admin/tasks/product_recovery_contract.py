"""Original product recovery descriptors, never a whole-site ResetReceipt."""

from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.state_scope import private_state_ref
from ..state_contract import AdminStateSnapshot, AdminStateRestored
from ..frontend_contract import AdminFrontendStopped


class ProductAbsence(Contract):
    schema_version: Literal["admin-product-absence/1"] = "admin-product-absence/1"
    product_id: int = Field(gt=0)
    absent: bool


class ProductRecoverySnapshot(Contract):
    schema_version: Literal["admin-product-recovery/2"] = "admin-product-recovery/2"
    request: SiteTaskRequest
    state: AdminStateSnapshot
    product: ProductAbsence

    @model_validator(mode="after")
    def captured(self) -> Self:
        if self.request.action != "snapshot" or not self.product.absent:
            raise ValueError("Recovery requires original pre-initialization snapshot")
        return self


class ProductRestored(Contract):
    schema_version: Literal["admin-product-restored/3"] = "admin-product-restored/3"
    task: TaskIdentity
    operation: OperationContext
    snapshot_ref: EvidenceRef
    state: AdminStateRestored
    frontend: AdminFrontendStopped
    product: ProductAbsence

    @model_validator(mode="after")
    def recovered(self) -> Self:
        private_state_ref(self.snapshot_ref, "admin-product-recovery/2")
        if self.frontend.service != self.state.search.original.service:
            raise ValueError("Product restore changed original frontend service")
        if self.operation.mode != "cleanup" or not self.product.absent:
            raise ValueError(
                "Product recovery needs actual cleanup and original absence"
            )
        return self
