"""Private product-description input, before preparation or execution admission.

Only PublicTask may flow to the Actor/Generator. The native reference retains
controls, baseline and lineage for trusted readers; none are executable here.
This contract does not assert saved state, reset health or training eligibility.
"""

from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.validation import Contract, NonEmptyText


class ProductDescriptionSpec(Contract):
    schema_version: Literal["shopping-admin-product-description/1"] = (
        "shopping-admin-product-description/1"
    )
    task: TaskIdentity
    native_contract_ref: EvidenceRef
    legacy_runtime_task_id: NonEmptyText
    product_id: int = Field(gt=0)
    store_id: int = Field(ge=0)
    product_name: NonEmptyText
    description: NonEmptyText
    admission: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def selected_family(self) -> Self:
        if (self.task.site, self.task.family, self.task.contract_version) != (
            "shopping_admin",
            "product_description",
            1,
        ):
            raise ValueError("Expected the current Admin product_description family")
        if (
            self.native_contract_ref.visibility,
            self.native_contract_ref.content_schema,
            self.native_contract_ref.media_type,
        ) != ("private", "admin-native-contract/1", "application/json"):
            raise ValueError("Original native contract must remain private JSON")
        return self


class ProductDescriptionInputs(Contract):
    """Trusted bootstrap result, never itself a model prompt or PreparedTask."""

    schema_version: Literal["shopping-admin-product-description-inputs/1"] = (
        "shopping-admin-product-description-inputs/1"
    )
    public_task: PublicTask
    private_spec: ProductDescriptionSpec

    @model_validator(mode="after")
    def same_task(self) -> Self:
        if self.public_task.identity != self.private_spec.task:
            raise ValueError(
                "Public and private description inputs identify different tasks"
            )
        return self
