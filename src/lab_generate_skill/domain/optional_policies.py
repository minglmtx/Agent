"""Explicit optional strategy choices frozen before any runtime assembly.

Disabled/not-applicable choices contain no implementation or resource reference.
An enabled choice pins both execution and independent review, but a reference
to validation evidence is not itself approval: admission must inspect its bytes
and verify the actual release, compatibility and source of that evidence.
"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .evidence import EvidenceRef
from .state_scope import private_state_ref
from .validation import Contract, Identifier, NonEmptyText


class InactivePolicy(Contract):
    status: Literal["disabled", "not_applicable"]
    reason: NonEmptyText = Field(max_length=2048)


class EnabledPolicy(Contract):
    status: Literal["enabled"]
    reason: NonEmptyText = Field(max_length=2048)
    component_id: Identifier
    contract_version: str = Field(pattern=r"^[1-9][0-9]*\.[0-9]+$")
    configuration_ref: EvidenceRef
    reviewer_component_id: Identifier
    reviewer_contract_version: str = Field(pattern=r"^[1-9][0-9]*\.[0-9]+$")
    validation_ref: EvidenceRef

    @model_validator(mode="after")
    def evidence_pins(self) -> Self:
        private_state_ref(self.configuration_ref, "optional-policy-config/1")
        private_state_ref(self.validation_ref, "optional-policy-validation/1")
        if self.component_id == self.reviewer_component_id:
            raise ValueError("Execution policy and reviewer need distinct components")
        return self


PolicyChoice = Annotated[InactivePolicy | EnabledPolicy, Field(discriminator="status")]


class RunPolicies(Contract):
    schema_version: Literal["run-policies/1"] = "run-policies/1"
    actor_memory: PolicyChoice
    teacher_template: PolicyChoice

    def references(self) -> tuple[EvidenceRef, ...]:
        return tuple(
            dict.fromkeys(
                reference
                for choice in (self.actor_memory, self.teacher_template)
                if isinstance(choice, EnabledPolicy)
                for reference in (choice.configuration_ref, choice.validation_ref)
            )
        )
