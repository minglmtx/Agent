"""Single original public-row/settings/run-contract assembly for parent and worker."""

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from lab_generate_skill.domain.training import TrainingPlan
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.policies.training_admission import require_training_dataset
from .dataset_encoding import supervised_record


@dataclass(frozen=True)
class SFTInputs:
    args: argparse.Namespace
    train: list[dict[str, Any]]
    dev: list[dict[str, Any]]
    contract: dict[str, Any]


def build_sft_inputs(
    plan: TrainingPlan, data: LoadedDataset, output: Path
) -> SFTInputs:
    require_training_dataset(plan, data)
    assert data.manifest is not None
    rows = {
        i.example_id: e for i, e in zip(data.manifest.items, data.examples, strict=True)
    }
    train = [
        supervised_record(rows[i.example_id])
        for i in data.manifest.items
        if i.partition == "train"
    ]
    dev = [
        supervised_record(rows[i.example_id])
        for i in data.manifest.items
        if i.partition == "validation"
    ]
    options = plan.spec.model_dump(exclude={"schema_version"})
    args = argparse.Namespace(
        **options,
        output_dir=output,
        model=plan.model.root,
        model_id=plan.model.artifact_id,
        model_revision="frozen-training-plan",
        train_data="original-dataset:train",
        dev_data="original-dataset:validation",
    )
    # Fresh readonly operation deadlines do not change checkpoint lineage.
    # Source receipt, all row refs, original settings/model/release stay fixed.
    fixed_options = {
        k: v
        for k, v in options.items()
        if k not in {"resume", "save_steps", "log_steps"}
    }
    contract = dict(
        schema_version="sft-run-contract/1",
        training_id=plan.training_id,
        dataset_ref=(
            data.receipt.dataset_ref.model_dump(mode="json")
            if data.receipt.dataset_ref is not None
            else None
        ),
        export_receipt_ref=plan.dataset.export_receipt_ref.model_dump(mode="json"),
        model=plan.model.model_dump(mode="json"),
        training_release_ref=plan.training_release_ref.model_dump(mode="json"),
        phase_authorization_ref=plan.phase_authorization_ref.model_dump(mode="json"),
        settings=fixed_options,
        example_refs=[
            i.example_ref.model_dump(mode="json") for i in data.manifest.items
        ],
    )
    return SFTInputs(args, train, dev, contract)
