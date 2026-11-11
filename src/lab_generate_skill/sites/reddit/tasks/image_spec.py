"""Selected derived media meaning and private lineage; no execution permission."""

from typing import Literal, Self
from pydantic import model_validator
from lab_generate_skill.domain.validation import Contract, NonEmptyText
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask
from .image_parameters import ImageParameters, render_public_goal

OUTPUT_REQUIREMENTS = (
    "Finish with send_msg_to_user after checking whether the native post saved the supplied photograph.",
)


class NativeImageSpec(Contract):
    schema_version: Literal["reddit-native-image/1"] = "reddit-native-image/1"
    task: TaskIdentity
    native_contract_ref: EvidenceRef
    legacy_runtime_task_id: NonEmptyText
    native_goal: NonEmptyText
    parameters: ImageParameters
    admission: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def selected(self) -> Self:
        if (
            self.task.site,
            self.task.family,
            self.task.contract_version,
            self.task.split,
        ) != ("reddit", "native_image_submission", 1, "train"):
            raise ValueError(
                "Selected derived train Reddit native-image family required"
            )
        if (
            self.legacy_runtime_task_id
            != self.task.source_task_id + "--native-media-cpu-v1"
        ):
            raise ValueError("Original native media derivative lineage changed")
        if (
            self.native_contract_ref.visibility,
            self.native_contract_ref.media_type,
            self.native_contract_ref.content_schema,
        ) != ("private", "application/json", "reddit-native-contract/1"):
            raise ValueError("Original private native Reddit contract required")
        return self


class NativeImageInputs(Contract):
    schema_version: Literal["reddit-native-image-inputs/1"] = (
        "reddit-native-image-inputs/1"
    )
    public_task: PublicTask
    private_spec: NativeImageSpec

    @model_validator(mode="after")
    def same_public_meaning(self) -> Self:
        if (
            self.public_task.identity != self.private_spec.task
            or self.public_task.goal
            != render_public_goal(
                self.private_spec.native_goal, self.private_spec.parameters
            )
        ):
            raise ValueError(
                "Original public native-image parameters or identity changed"
            )
        return self
