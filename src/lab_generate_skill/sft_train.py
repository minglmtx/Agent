#!/usr/bin/env python3
"""Compatibility helpers and the qualified WebArena generator training entry.

Adapted from generative_skill/scripts/train_qwen3_generator_lora.py,
commit f236a30aa10974d8614cb84d91a499c0d394a78a."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import signal
import tempfile
import time
from functools import partial
from pathlib import Path
from typing import Any, Mapping, Sequence
from .adapters.training.supervised_encoding import token_ids, encode_supervised_record
from .adapters.training.files import (
    atomic_json,
    append_jsonl,
    latest_checkpoint,
    sha_file,
    check_run_contract,
)
from .adapters.training.torch_sft import collate_examples
from .bootstrap.training_entry import main


def load_jsonl(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"expected JSON object in {path}")
                records.append(value)
                if limit is not None and len(records) >= limit:
                    break
    if not records:
        raise ValueError(f"empty dataset: {path}")
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-id", default="Qwen/Qwen3-8B")
    parser.add_argument("--model-revision", default="local-snapshot")
    parser.add_argument("--train-data", type=Path, required=True)
    parser.add_argument("--dev-data", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-seq-length", type=int, default=4096)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--per-device-batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--weight-decay", type=float, default=0.0)
    parser.add_argument("--warmup-ratio", type=float, default=0.03)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--save-steps", type=int, default=50)
    parser.add_argument("--log-steps", type=int, default=5)
    parser.add_argument(
        "--max-steps",
        type=int,
        help="Cap optimizer updates within the requested epochs",
    )
    parser.add_argument("--train-limit", type=int)
    parser.add_argument("--dev-limit", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    positive = (
        "max_seq_length",
        "epochs",
        "per_device_batch_size",
        "gradient_accumulation_steps",
        "learning_rate",
        "max_grad_norm",
        "lora_r",
        "lora_alpha",
        "save_steps",
        "log_steps",
    )
    for name in positive:
        if not math.isfinite(getattr(args, name)) or getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be finite and positive")
    for name in ("max_steps", "train_limit", "dev_limit"):
        if getattr(args, name) is not None and getattr(args, name) < 1:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    if not math.isfinite(args.weight_decay) or args.weight_decay < 0:
        parser.error("--weight-decay must be finite and nonnegative")
    if not math.isfinite(args.warmup_ratio) or not 0 <= args.warmup_ratio <= 1:
        parser.error("--warmup-ratio must be between zero and one")
    if not math.isfinite(args.lora_dropout) or not 0 <= args.lora_dropout < 1:
        parser.error("--lora-dropout must be at least zero and below one")
    return args


def run_contract(args, *, runtime_bank_path=None) -> dict:
    values = {
        k: str(v) if isinstance(v, Path) else v
        for k, v in vars(args).items()
        if k not in {"resume", "output_dir", "log_steps", "save_steps"}
    }
    values["train_sha256"] = sha_file(args.train_data)
    values["dev_sha256"] = sha_file(args.dev_data)
    values["implementation_sha256"] = sha_file(Path(__file__))
    if runtime_bank_path is not None:
        values["runtime_bank_sha256"] = sha_file(runtime_bank_path)
    model_path = Path(args.model)
    if not model_path.is_dir():
        raise ValueError("A local model directory is required")
    values["model_files"] = {
        p.name: sha_file(p) for p in sorted(model_path.glob("*.json"))
    }
    return values


def require_training_sft_record(record):
    """Keep engineering exports out of the parameter-training entry point.

    The upstream exporter still verifies the actual Stage-1 evidence. These
    labels are an additional admission check, not a replacement for that review.
    """
    metadata = record.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("SFT requires labeled Stage-1 training targets")
    if (
        metadata.get("training_data") is not True
        or metadata.get("output_purpose") != "training"
        or metadata.get("target_status") != "environment_verified"
    ):
        raise ValueError(
            "SFT requires verified Stage-1 training targets; pilot, offline and unlabeled records are excluded"
        )
    models = metadata.get("models", {})
    if not isinstance(models, dict):
        raise ValueError("Invalid Stage-1 model metadata")
    if (
        metadata.get("teacher_mode") == "local_replacement"
        or models.get("teacher_mode") == "local_replacement"
    ):
        raise ValueError("Local replacement Teacher targets remain engineering pilots")


def validate_sft_splits(train, dev):
    from .schemas import CompactSkill

    for split in (train, dev):
        if len({r["id"] for r in split}) != len(split):
            raise ValueError("Duplicate SFT record IDs")
        for r in split:
            require_training_sft_record(r)
            CompactSkill.model_validate(json.loads(r["messages"][-1]["content"]))
            if not r.get("goal_group_id") or not r.get("task_id"):
                raise ValueError("SFT records need task_id and goal_group_id")
    # Similar skill text across distinct tasks is valid supervision. Bank
    # clustering must not remove task/context examples or constrain their split.
    for key in ("id", "goal_group_id", "task_id"):
        if {r[key] for r in train} & {r[key] for r in dev}:
            raise ValueError("Train/dev leakage: " + key)


if __name__ == "__main__":
    main()
