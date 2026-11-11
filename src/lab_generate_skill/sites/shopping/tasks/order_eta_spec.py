"""Private recorded ETA fixture, separate from the approved public task."""

from typing import Annotated, Literal, Self
from datetime import date
from pydantic import Field, field_validator, model_validator
from lab_generate_skill.domain.validation import Contract, NonEmptyText
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask

OrderNumber = Annotated[str, Field(pattern=r"\A[0-9]{9}\z")]
RecordedDate = Annotated[str, Field(pattern=r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}\z")]
OUTPUT_REQUIREMENTS = (
    "Finish with send_msg_to_user containing one JSON object with exactly the field estimated_delivery_date, a YYYY-MM-DD string read from the customer-visible order comments.",
    "Read the requested order without modifying site records. Preserve leading zeros in order identifiers.",
)


class OrderEtaSpec(Contract):
    schema_version: Literal["shopping-recorded-order-eta/1"] = (
        "shopping-recorded-order-eta/1"
    )
    task: TaskIdentity
    native_contract_ref: EvidenceRef
    legacy_runtime_task_id: NonEmptyText
    order_number: OrderNumber
    recorded_date: RecordedDate
    fixture_version: Literal["native-local-recorded-order-date-v1"] = (
        "native-local-recorded-order-date-v1"
    )
    admission: Literal["unverified"] = "unverified"

    @field_validator("recorded_date")
    @classmethod
    def calendar_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def selected_family(self) -> Self:
        if (
            self.task.site,
            self.task.family,
            self.task.contract_version,
            self.task.split,
        ) != ("shopping", "recorded_order_eta", 1, "train"):
            raise ValueError("Expected the selected derived train Shopping ETA family")
        if (
            self.native_contract_ref.visibility,
            self.native_contract_ref.content_schema,
            self.native_contract_ref.media_type,
        ) != ("private", "shopping-native-contract/1", "application/json"):
            raise ValueError("Original Shopping contract must remain private JSON")
        if (
            self.legacy_runtime_task_id
            != self.task.source_task_id + "--complete-native-training-v1"
        ):
            raise ValueError(
                "Historical Shopping derivative has different source lineage"
            )
        return self


class OrderEtaInputs(Contract):
    schema_version: Literal["shopping-recorded-order-eta-inputs/1"] = (
        "shopping-recorded-order-eta-inputs/1"
    )
    public_task: PublicTask
    private_spec: OrderEtaSpec

    @model_validator(mode="after")
    def same_task(self) -> Self:
        if self.public_task.identity != self.private_spec.task:
            raise ValueError("Public and private ETA inputs identify different tasks")
        return self
