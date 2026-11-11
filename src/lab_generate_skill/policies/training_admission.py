"""Revalidate the complete common dataset before any tokenizer/training effects."""

from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.domain.training import TrainingPlan
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.policies.dataset_split import normalize_goal
from lab_generate_skill.policies.dataset_manifest import (
    export_metadata,
    example_reference,
)
from lab_generate_skill.domain.evidence_identity import evidence_reference


def require_training_dataset(plan: TrainingPlan, data: LoadedDataset) -> None:
    if (data.purpose, data.receipt.kind, data.receipt.status) != (
        "sft",
        "formal",
        "train_validation_ready",
    ) or data.manifest is None:
        raise EvidenceIntegrityError(
            "SFT requires qualified formal nonempty data and the original viable split"
        )
    m = data.manifest
    if (
        plan.dataset.export_receipt_ref
        != evidence_reference(
            data.receipt.model_dump_json().encode(), export_metadata("export-receipt/1")
        )
        or data.receipt.dataset_ref
        != evidence_reference(
            m.model_dump_json().encode(), export_metadata("dataset-manifest/1")
        )
        or m.export_plan_ref != data.receipt.export_plan_ref
    ):
        raise EvidenceIntegrityError(
            "Training view changed the original receipt/manifest identity"
        )
    if (
        m.kind != "formal"
        or m.status != "train_validation_ready"
        or not data.examples
        or len(data.examples) != len(m.items)
        or data.receipt.example_count != len(data.examples)
    ):
        raise EvidenceIntegrityError(
            "Training dataset differs from the complete original manifest"
        )
    train = []
    valid = []
    for item, example in zip(m.items, data.examples, strict=True):
        if (
            example.kind != "formal"
            or not example.labels.formal()
            or example.task.split != "train"
            or item.example_id != example.example_id
            or item.example_ref != example_reference(example)
            or (example.export_plan_ref, example.scope_ref, example.split_ref)
            != (m.export_plan_ref, m.scope_ref, m.split_ref)
        ):
            raise EvidenceIntegrityError(
                "Fixture/heldout/relabeled rows cannot enter parameter training"
            )
        if item.partition == "train":
            train.append(example)
        elif item.partition == "validation":
            valid.append(example)
        else:
            raise EvidenceIntegrityError("Candidate accumulation cannot enter SFT")
    if not train or not valid:
        raise EvidenceIntegrityError(
            "Original goal groups must support both train and validation"
        )
    for values in (
        lambda e: e.example_id,
        lambda e: e.task.task_id,
        lambda e: e.goal_group_id,
        lambda e: normalize_goal(e.group_goal),
    ):
        if {values(e) for e in train}.intersection(values(e) for e in valid):
            raise EvidenceIntegrityError(
                "Training/validation leak an original task or normalized goal group"
            )
