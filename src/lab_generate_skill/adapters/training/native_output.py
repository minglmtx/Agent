"""Check native output against original source/contract, preserve opaque full files."""

import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any
from lab_generate_skill.domain.training import TrainingSpec
from lab_generate_skill.domain.training_output import (
    TrainingOutputPlan,
    NativeSFTOutcome,
    NativeSFTSummary,
)
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.domain.release import ReleaseArtifact
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.releases.file_read import frozen_bytes
from lab_generate_skill.adapters.processes.wire_json import json_object
from .inputs import build_sft_inputs


def native_training_outcome(
    plan: TrainingOutputPlan,
    data: LoadedDataset,
    artifact: ReleaseArtifact,
    control: OperationControl,
) -> NativeSFTOutcome:
    request = build_sft_inputs(plan.training, data, Path(plan.output_root))
    members = {f.path: f for f in artifact.files}

    def document(name: str) -> dict[str, Any]:
        entry = members.get(name)
        if entry is None or not 0 < entry.size_bytes <= 8 * 1024**2:
            raise EvidenceIntegrityError(
                "Missing or oversized complete native JSON member: " + name
            )
        return json_object(frozen_bytes(Path(artifact.root), entry, control))

    def same(a: object, b: object) -> bool:
        return json.dumps(a, ensure_ascii=False, sort_keys=True) == json.dumps(
            b, ensure_ascii=False, sort_keys=True
        )

    if not same(document("run_manifest.json"), request.contract):
        raise EvidenceIntegrityError(
            "Native run manifest changed original training contract"
        )
    config = document("training_config.json")
    base = {
        **vars(request.args),
        "output_dir": str(request.args.output_dir),
        "train_data": str(request.args.train_data),
        "dev_data": str(request.args.dev_data),
    }
    extras = {
        "train_rows",
        "dev_rows",
        "trainable_parameters",
        "total_parameters",
        "planned_optimizer_steps",
        "optimizer_steps_for_all_epochs",
        "warmup_steps",
        "dtype",
        "attention_implementation",
        "assistant_loss_mask",
    }
    if set(config) != set(base) | extras:
        raise EvidenceIntegrityError(
            "Native configuration has missing/unhandled fields"
        )
    mutable = {"resume", "save_steps", "log_steps"}
    option_keys = set(plan.training.spec.model_dump(exclude={"schema_version"}))
    TrainingSpec.model_validate({k: config[k] for k in option_keys})
    if not same(
        {k: config[k] for k in base if k not in mutable},
        {k: v for k, v in base.items() if k not in mutable},
    ):
        raise EvidenceIntegrityError("Native model/settings/input scope changed")
    if not plan.training.spec.resume and config["resume"] is not False:
        raise EvidenceIntegrityError(
            "Native resume requires original explicit resume permission"
        )
    s = plan.training.spec
    ntrain = min(len(request.train), s.train_limit or len(request.train))
    ndev = min(len(request.dev), s.dev_limit or len(request.dev))
    all_steps = (
        math.ceil(
            math.ceil(ntrain / s.per_device_batch_size) / s.gradient_accumulation_steps
        )
        * s.epochs
    )
    total = min(all_steps, s.max_steps) if s.max_steps is not None else all_steps
    integers = {
        "train_rows": ntrain,
        "dev_rows": ndev,
        "planned_optimizer_steps": total,
        "optimizer_steps_for_all_epochs": all_steps,
        "warmup_steps": round(total * s.warmup_ratio),
    }
    if (
        any(type(config[k]) is not int or config[k] != v for k, v in integers.items())
        or any(
            type(config[k]) is not int
            for k in ("trainable_parameters", "total_parameters")
        )
        or not 0 < config["trainable_parameters"] < config["total_parameters"]
    ):
        raise EvidenceIntegrityError(
            "Native row/optimizer/parameter counts do not match original input"
        )
    if (
        config["dtype"],
        config["attention_implementation"],
        config["assistant_loss_mask"],
    ) != ("bfloat16", "sdpa", "prompt prefix labels are -100"):
        raise EvidenceIntegrityError("Native dtype/attention/supervision changed")
    checkpoints = []
    for name in members:
        match = re.fullmatch(r"(checkpoint-([0-9]{6}))/complete.json", name)
        if match:
            marker = document(name)
            step = int(match[2])
            if (
                set(marker) != {"complete", "step"}
                or marker["complete"] is not True
                or type(marker["step"]) is not int
                or marker["step"] != step
                or not 0 < step <= total
            ):
                raise EvidenceIntegrityError(
                    "Native checkpoint complete marker is invalid"
                )
            checkpoints.append((step, match[1]))
    if not checkpoints:
        raise EvidenceIntegrityError("No complete original checkpoint exists")
    step, selected = max(checkpoints)
    required = {
        "metrics.jsonl",
        "tokenizer/tokenizer_config.json",
        "tokenizer/tokenizer.json",
        selected + "/training_state.pt",
        selected + "/adapter/adapter_config.json",
        selected + "/adapter/adapter_model.safetensors",
    }
    status = "stopped"
    if "training_summary.json" in members:
        raw = document("training_summary.json")
        if raw.get("complete") is not True:
            raise EvidenceIntegrityError(
                "Native summary has no exact completed boolean"
            )
        summary = NativeSFTSummary.model_validate_json(json.dumps(raw).encode())
        if (
            summary.global_step,
            summary.planned_optimizer_steps,
            summary.train_rows,
            summary.dev_rows,
            summary.max_seq_length,
            summary.max_steps_limited,
        ) != (
            step,
            total,
            ntrain,
            ndev,
            s.max_seq_length,
            s.max_steps is not None and s.max_steps < all_steps,
        ):
            raise EvidenceIntegrityError(
                "Native final summary differs from source/config/checkpoint"
            )
        if summary.global_step != total or summary.epochs_visited > s.epochs:
            raise EvidenceIntegrityError(
                "Native completion did not execute every planned optimizer update"
            )
        required |= {
            "final_adapter/adapter_config.json",
            "final_adapter/adapter_model.safetensors",
        }
        status = "completed"
    if any(name not in members or members[name].size_bytes == 0 for name in required):
        raise EvidenceIntegrityError(
            "Native tokenizer/checkpoint/adapter/log evidence is incomplete"
        )
    return NativeSFTOutcome.model_validate(
        dict(
            status=status,
            optimizer_steps=step,
            planned_optimizer_steps=total,
            selected_checkpoint=selected,
            contract_sha256=hashlib.sha256(
                json.dumps(
                    request.contract, ensure_ascii=False, sort_keys=True
                ).encode()
            ).hexdigest(),
        )
    )
