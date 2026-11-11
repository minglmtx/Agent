"""One versioned export/consumer schema; fixture artifacts never grant training."""

from typing import Literal, Self, Final
import hashlib
import json
from pydantic import Field, model_validator
from .validation import Contract, Identifier, NonEmptyText
from .identity import TaskIdentity
from .evidence import EvidenceRef
from .skill import CompactSkill
from .state_scope import private_state_ref

DatasetKind = Literal["formal", "engineering_fixture"]
DATASET_TEMPLATE: Final = "webarena-generator-v6-actor-capabilities"


class TrainingLabels(Contract):
    training_data: bool
    output_purpose: Literal["training", "engineering"]
    target_status: Literal[
        "environment_verified", "interface_verified", "pilot", "offline"
    ]
    teacher_mode: Literal["authorized_api", "local_replacement", "fixture"]

    def formal(self) -> bool:
        return (
            self.training_data,
            self.output_purpose,
            self.target_status,
            self.teacher_mode,
        ) == (True, "training", "environment_verified", "authorized_api")


class SFTMessage(Contract):
    role: Literal["system", "user", "assistant"]
    content: NonEmptyText


class TrainingExample(Contract):
    schema_version: Literal["training-example/1"] = "training-example/1"
    kind: DatasetKind
    example_id: Identifier
    legacy_id: Identifier
    task: TaskIdentity
    goal_group_id: Identifier
    group_goal: NonEmptyText
    export_plan_ref: EvidenceRef
    scope_ref: EvidenceRef
    split_ref: EvidenceRef
    bank_ref: EvidenceRef
    retrieval_ref: EvidenceRef
    generation_input_ref: EvidenceRef
    target_skill_ref: EvidenceRef
    selected_evaluation_ref: EvidenceRef
    review_ref: EvidenceRef
    qualification_ref: EvidenceRef
    labels: TrainingLabels
    template: Literal[
        "webarena-generator-v6-actor-capabilities",
        "webarena-generator-v7-selected-actor",
    ] = DATASET_TEMPLATE
    messages: tuple[SFTMessage, SFTMessage, SFTMessage]

    @model_validator(mode="after")
    def bound_public_supervision(self) -> Self:
        if (
            self.task.split != "train"
            or self.example_id != self.legacy_id
            or self.legacy_id != self.task.task_id
        ):
            raise ValueError(
                "Explicit original task/id mapping and train-only sources required"
            )
        if tuple(m.role for m in self.messages) != ("system", "user", "assistant"):
            raise ValueError(
                "One frozen Generator prompt and one complete skill target required"
            )
        target = json.loads(self.messages[-1].content)
        skill = CompactSkill.model_validate(target)
        if self.messages[-1].content != json.dumps(
            skill.model_payload(), ensure_ascii=False
        ):
            raise ValueError("Exact canonical three-field assistant skill required")
        if self.kind == "formal" and not self.labels.formal():
            raise ValueError(
                "Formal samples require original verified authorized training labels"
            )
        if self.kind == "engineering_fixture" and (
            self.labels.training_data
            or self.labels.output_purpose != "engineering"
            or self.labels.target_status != "interface_verified"
            or self.labels.teacher_mode != "fixture"
        ):
            raise ValueError("Fixture examples must remain visibly nontraining")
        for ref, schema in (
            (self.export_plan_ref, "export-plan/1"),
            (self.scope_ref, "export-scope/1"),
            (self.split_ref, "data-split/1"),
            (self.bank_ref, "bank-manifest/1"),
            (self.retrieval_ref, "retrieval-result/1"),
            (self.selected_evaluation_ref, "evaluation/1"),
            (self.review_ref, "construction-review-receipt/1"),
            (self.qualification_ref, "training-target-qualification/1"),
        ):
            private_state_ref(ref, schema)
        for ref, schema in (
            (
                self.generation_input_ref,
                (
                    "generation-input/2"
                    if self.template == "webarena-generator-v7-selected-actor"
                    else "generation-input/1"
                ),
            ),
            (self.target_skill_ref, "compact-skill/1"),
        ):
            if (ref.visibility, ref.content_schema, ref.media_type) != (
                "public",
                schema,
                "application/json",
            ):
                raise ValueError("Original public Generator/target references required")
        if len(self.model_dump_json().encode()) > 8 * 1024**2:
            raise ValueError("Complete example exceeds metadata bound; never truncate")
        return self


class DatasetItem(Contract):
    example_id: Identifier
    partition: Literal["train", "validation", "candidate"]
    example_ref: EvidenceRef

    @model_validator(mode="after")
    def private_row(self) -> Self:
        private_state_ref(self.example_ref, "training-example/1")
        return self


class DatasetManifest(Contract):
    schema_version: Literal["dataset-manifest/1"] = "dataset-manifest/1"
    kind: DatasetKind
    export_plan_ref: EvidenceRef
    scope_ref: EvidenceRef
    split_ref: EvidenceRef
    template: Literal[
        "webarena-generator-v6-actor-capabilities",
        "webarena-generator-v7-selected-actor",
    ] = DATASET_TEMPLATE
    split_policy: Literal["frozen-member-goal-stratified-v1"] = (
        "frozen-member-goal-stratified-v1"
    )
    status: Literal["train_validation_ready", "awaiting_goal_groups"]
    items: tuple[DatasetItem, ...] = Field(min_length=1, max_length=900)
    bank_refs: tuple[EvidenceRef, ...] = Field(min_length=1, max_length=900)
    review_refs: tuple[EvidenceRef, ...] = Field(min_length=1, max_length=900)
    examples_sha256: str

    @model_validator(mode="after")
    def exact_manifest(self) -> Self:
        if len({i.example_id for i in self.items}) != len(self.items):
            raise ValueError("Duplicate exported example identity")
        parts = {i.partition for i in self.items}
        expected = (
            {"train", "validation"}
            if self.status == "train_validation_ready"
            else {"candidate"}
        )
        if parts != expected:
            raise ValueError(
                "Dataset must preserve ready split or explicit accumulation state"
            )
        for ref, schema in (
            (self.export_plan_ref, "export-plan/1"),
            (self.scope_ref, "export-scope/1"),
            (self.split_ref, "data-split/1"),
        ):
            private_state_ref(ref, schema)
        for refs, schema in (
            (self.bank_refs, "bank-manifest/1"),
            (self.review_refs, "construction-review-receipt/1"),
        ):
            if len(set(refs)) != len(refs):
                raise ValueError("Duplicate manifest dependency")
            for ref in refs:
                private_state_ref(ref, schema)
        expected_digest = hashlib.sha256(
            json.dumps(
                [i.model_dump(mode="json") for i in self.items],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if (
            self.examples_sha256 != expected_digest
            or len(self.model_dump_json().encode()) > 4 * 1024**2
        ):
            raise ValueError(
                "Manifest must bind complete ordered example refs and partitions"
            )
        return self
