"""Original single-GPU LoRA algorithm, shared engine leaf; no dataset discovery.

Run only inside an authorized supervised training runtime. Caller owns the
original run manifest/checkpoint directory and physical worker termination.
"""

import argparse
from functools import partial
from importlib import import_module
import json
import math
import os
from pathlib import Path
import random
import signal
import time
import threading
from typing import Any, Sequence
from lab_generate_skill.ports.lifecycle import OperationControl
from .files import atomic_json, append_jsonl, latest_checkpoint, check_run_contract
from .supervised_encoding import encode_supervised_record


def collate_examples(
    examples: Sequence[dict[str, Any]], *, pad_token_id: int, pad_to_multiple: int = 8
) -> dict[str, Any]:
    torch = import_module("torch")

    longest = max(len(example["input_ids"]) for example in examples)
    padded = math.ceil(longest / pad_to_multiple) * pad_to_multiple
    input_ids: list[list[int]] = []
    labels: list[list[int]] = []
    attention_mask: list[list[int]] = []
    for example in examples:
        amount = padded - len(example["input_ids"])
        input_ids.append(example["input_ids"] + [pad_token_id] * amount)
        labels.append(example["labels"] + [-100] * amount)
        attention_mask.append([1] * len(example["input_ids"]) + [0] * amount)
    return {
        "input_ids": torch.tensor(input_ids, dtype=torch.long),
        "labels": torch.tensor(labels, dtype=torch.long),
        "attention_mask": torch.tensor(attention_mask, dtype=torch.long),
    }


def _run_original_sft(
    args: argparse.Namespace,
    all_train: list[dict[str, Any]],
    all_dev: list[dict[str, Any]],
    contract: dict[str, Any],
    control: OperationControl,
) -> None:
    control.checkpoint()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    np = import_module("numpy")
    torch = import_module("torch")
    peft = import_module("peft")
    LoraConfig, PeftModel, get_peft_model = (
        peft.LoraConfig,
        peft.PeftModel,
        peft.get_peft_model,
    )
    DataLoader = import_module("torch.utils.data").DataLoader
    transformers = import_module("transformers")
    AutoModelForCausalLM, AutoTokenizer = (
        transformers.AutoModelForCausalLM,
        transformers.AutoTokenizer,
    )
    get_cosine_schedule_with_warmup = transformers.get_cosine_schedule_with_warmup

    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("training requires a CUDA GPU with bfloat16 support")
    check_run_contract(args.output_dir, contract, args.resume)
    completed_summary = args.output_dir / "training_summary.json"
    if completed_summary.exists():
        summary = json.loads(completed_summary.read_text(encoding="utf-8"))
        if summary.get("complete"):
            print(json.dumps(summary, indent=2))
            return
    args.output_dir.mkdir(parents=True, exist_ok=True)

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

    control.checkpoint()
    tokenizer = AutoTokenizer.from_pretrained(
        args.model, local_files_only=True, trust_remote_code=False
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    raw_train = all_train[: args.train_limit] if args.train_limit else all_train
    raw_dev = all_dev[: args.dev_limit] if args.dev_limit else all_dev
    train_data = [
        encode_supervised_record(tokenizer, record, max_seq_length=args.max_seq_length)
        for record in raw_train
    ]
    dev_data = [
        encode_supervised_record(tokenizer, record, max_seq_length=args.max_seq_length)
        for record in raw_dev
    ]
    collator = partial(collate_examples, pad_token_id=int(tokenizer.pad_token_id))
    dev_loader = DataLoader(
        dev_data,
        batch_size=args.per_device_batch_size,
        shuffle=False,
        num_workers=0,
        collate_fn=collator,
        # DataLoader creates an iterator seed even with zero workers. Keep
        # resume-time evaluation from advancing the training dropout RNG.
        generator=torch.Generator().manual_seed(args.seed),
    )

    checkpoint = latest_checkpoint(args.output_dir) if args.resume else None
    base = AutoModelForCausalLM.from_pretrained(
        args.model,
        local_files_only=True,
        trust_remote_code=False,
        torch_dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
        attn_implementation="sdpa",
    )
    base.config.use_cache = False
    if checkpoint is None:
        lora_config = LoraConfig(
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=args.lora_dropout,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=[
                "q_proj",
                "k_proj",
                "v_proj",
                "o_proj",
                "gate_proj",
                "up_proj",
                "down_proj",
            ],
        )
        model = get_peft_model(base, lora_config)
    else:
        model = PeftModel.from_pretrained(
            base, checkpoint / "adapter", is_trainable=True
        )
    model.enable_input_require_grads()
    model.gradient_checkpointing_enable(
        gradient_checkpointing_kwargs={"use_reentrant": False}
    )
    model.to("cuda")
    model.train()
    tokenizer.save_pretrained(args.output_dir / "tokenizer")

    trainable = sum(
        parameter.numel() for parameter in model.parameters() if parameter.requires_grad
    )
    total = sum(parameter.numel() for parameter in model.parameters())
    if not 0 < trainable < total:
        raise RuntimeError(f"invalid trainable parameter count: {trainable}/{total}")
    print(
        f"trainable parameters: {trainable:,}/{total:,} ({100 * trainable / total:.4f}%)"
    )

    batches_per_epoch = math.ceil(len(train_data) / args.per_device_batch_size)
    updates_per_epoch = math.ceil(batches_per_epoch / args.gradient_accumulation_steps)
    planned_steps = updates_per_epoch * args.epochs
    total_steps = (
        min(args.max_steps, planned_steps)
        if args.max_steps is not None
        else planned_steps
    )
    warmup_steps = round(total_steps * args.warmup_ratio)
    parameters = [
        parameter for parameter in model.parameters() if parameter.requires_grad
    ]
    try:
        optimizer = torch.optim.AdamW(
            parameters,
            lr=args.learning_rate,
            betas=(0.9, 0.999),
            eps=1e-8,
            weight_decay=args.weight_decay,
            fused=True,
        )
    except TypeError:
        optimizer = torch.optim.AdamW(
            parameters,
            lr=args.learning_rate,
            betas=(0.9, 0.999),
            eps=1e-8,
            weight_decay=args.weight_decay,
        )
    scheduler = get_cosine_schedule_with_warmup(optimizer, warmup_steps, total_steps)

    start_epoch = 0
    start_batch = 0
    global_step = 0
    checkpoint_reporting: dict[str, Any] | None = None
    if checkpoint is not None:
        state = torch.load(
            checkpoint / "training_state.pt", map_location="cpu", weights_only=False
        )
        optimizer.load_state_dict(state["optimizer"])
        scheduler.load_state_dict(state["scheduler"])
        start_epoch = int(state["epoch"])
        start_batch = int(state["next_batch"])
        global_step = int(state["global_step"])
        checkpoint_reporting = state["reporting"]
        random.setstate(state["python_rng"])
        np.random.set_state(state["numpy_rng"])
        torch.set_rng_state(state["torch_rng"])
        torch.cuda.set_rng_state_all(state["cuda_rng"])
        print(
            f"resuming {checkpoint} at epoch={start_epoch} batch={start_batch} step={global_step}"
        )

    configuration = {
        **vars(args),
        "train_data": str(args.train_data),
        "dev_data": str(args.dev_data),
        "output_dir": str(args.output_dir),
        "train_rows": len(train_data),
        "dev_rows": len(dev_data),
        "trainable_parameters": trainable,
        "total_parameters": total,
        "planned_optimizer_steps": total_steps,
        "optimizer_steps_for_all_epochs": planned_steps,
        "warmup_steps": warmup_steps,
        "dtype": "bfloat16",
        "attention_implementation": "sdpa",
        "assistant_loss_mask": "prompt prefix labels are -100",
    }
    atomic_json(args.output_dir / "training_config.json", configuration)
    metrics_path = args.output_dir / "metrics.jsonl"
    stop_requested = False
    epoch_metrics: list[dict[str, Any]] = (
        list(checkpoint_reporting["eval_metrics"]) if checkpoint_reporting else []
    )
    initial_eval_loss = (
        checkpoint_reporting["initial_eval_loss"] if checkpoint_reporting else None
    )
    previous_elapsed: float = (
        checkpoint_reporting["elapsed_seconds"] if checkpoint_reporting else 0.0
    )
    previous_peak: float = (
        checkpoint_reporting["peak_memory_gib"] if checkpoint_reporting else 0.0
    )

    def request_stop(signum: int, _frame: Any) -> None:
        nonlocal stop_requested
        print(
            f"received signal {signum}; checkpointing after the current optimizer step"
        )
        stop_requested = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGUSR1, request_stop)

    def evaluate(step: int, epoch: int, *, kind: str = "epoch") -> float:
        model.eval()
        weighted_loss = 0.0
        supervised_tokens = 0
        with torch.no_grad():
            for batch in dev_loader:
                control.checkpoint()
                batch = {
                    key: value.to("cuda", non_blocking=True)
                    for key, value in batch.items()
                }
                output = model(**batch)
                if not torch.isfinite(output.loss).item():
                    raise FloatingPointError(
                        "Nonfinite dev loss; training cannot be marked complete"
                    )
                tokens = int((batch["labels"] != -100).sum().item())
                weighted_loss += float(output.loss.item()) * tokens
                supervised_tokens += tokens
        loss = weighted_loss / supervised_tokens
        model.train()
        append_jsonl(
            metrics_path,
            {
                "event": "eval",
                "step": step,
                "epoch": epoch,
                "loss": loss,
                "tokens": supervised_tokens,
                "evaluation_kind": kind,
            },
        )
        print(f"eval step={step} epoch={epoch} loss={loss:.6f}")
        epoch_metrics.append(
            {"step": step, "epoch": epoch, "loss": loss, "evaluation_kind": kind}
        )
        return loss

    def save_checkpoint(epoch: int, next_batch: int) -> Path:
        destination: Path = args.output_dir / f"checkpoint-{global_step:06d}"
        if destination.exists():
            return destination
        temporary = args.output_dir / f".checkpoint-{global_step:06d}.tmp-{os.getpid()}"
        temporary.mkdir(parents=True, exist_ok=False)
        model.save_pretrained(temporary / "adapter", safe_serialization=True)
        torch.save(
            {
                "optimizer": optimizer.state_dict(),
                "scheduler": scheduler.state_dict(),
                "epoch": epoch,
                "next_batch": next_batch,
                "global_step": global_step,
                "python_rng": random.getstate(),
                "numpy_rng": np.random.get_state(),
                "torch_rng": torch.get_rng_state(),
                "cuda_rng": torch.cuda.get_rng_state_all(),
                "reporting": {
                    "initial_eval_loss": initial_eval_loss,
                    "eval_metrics": epoch_metrics,
                    "elapsed_seconds": previous_elapsed + time.monotonic() - started,
                    "peak_memory_gib": max(
                        previous_peak, torch.cuda.max_memory_allocated() / 2**30
                    ),
                },
            },
            temporary / "training_state.pt",
        )
        atomic_json(
            temporary / "complete.json", {"complete": True, "step": global_step}
        )
        os.replace(temporary, destination)
        return destination

    started = time.monotonic()
    invocation_initial_eval_loss = evaluate(
        global_step, start_epoch, kind="resume" if checkpoint else "initial"
    )
    if checkpoint is None:
        initial_eval_loss = invocation_initial_eval_loss
    final_eval_loss = invocation_initial_eval_loss
    optimizer.zero_grad(set_to_none=True)
    last_epoch = start_epoch
    finished = global_step >= total_steps
    for epoch in range(start_epoch, args.epochs):
        if finished:
            break
        last_epoch = epoch
        generator = torch.Generator()
        generator.manual_seed(args.seed + epoch)
        train_loader = DataLoader(
            train_data,
            batch_size=args.per_device_batch_size,
            shuffle=True,
            generator=generator,
            num_workers=0,
            collate_fn=collator,
        )
        skip = start_batch if epoch == start_epoch else 0
        accumulated_loss = 0.0
        for batch_index, batch in enumerate(train_loader):
            control.checkpoint()
            if batch_index < skip:
                continue
            group_start = (
                batch_index // args.gradient_accumulation_steps
            ) * args.gradient_accumulation_steps
            group_size = min(
                args.gradient_accumulation_steps, len(train_loader) - group_start
            )
            batch = {
                key: value.to("cuda", non_blocking=True) for key, value in batch.items()
            }
            output = model(**batch)
            if not torch.isfinite(output.loss).item():
                raise FloatingPointError(
                    "Nonfinite training loss; optimizer update refused"
                )
            loss = output.loss / group_size
            loss.backward()
            accumulated_loss += float(output.loss.detach().item())
            update = (
                batch_index + 1
            ) % args.gradient_accumulation_steps == 0 or batch_index + 1 == len(
                train_loader
            )
            if not update:
                continue
            grad_norm = float(
                torch.nn.utils.clip_grad_norm_(
                    parameters, args.max_grad_norm, error_if_nonfinite=True
                ).item()
            )
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad(set_to_none=True)
            global_step += 1
            train_loss = accumulated_loss / group_size
            accumulated_loss = 0.0
            if global_step % args.log_steps == 0 or global_step == 1:
                metric = {
                    "event": "train",
                    "step": global_step,
                    "epoch": epoch,
                    "batch": batch_index,
                    "loss": train_loss,
                    "grad_norm": grad_norm,
                    "learning_rate": scheduler.get_last_lr()[0],
                    "peak_memory_gib": round(
                        torch.cuda.max_memory_allocated() / 2**30, 3
                    ),
                }
                append_jsonl(metrics_path, metric)
                print(json.dumps(metric))
            if global_step % args.save_steps == 0 or stop_requested:
                saved = save_checkpoint(epoch, batch_index + 1)
                print(f"saved {saved}")
            if stop_requested:
                return
            if global_step >= total_steps:
                finished = True
                break
        final_eval_loss = evaluate(global_step, epoch + 1)
        save_checkpoint(epoch + 1, 0)
        start_batch = 0
        if finished:
            break

    if global_step != total_steps:
        raise RuntimeError(
            f"Training stopped at {global_step} of {total_steps} planned optimizer updates"
        )
    final_adapter = args.output_dir / "final_adapter"
    if not final_adapter.exists():
        temporary_adapter = args.output_dir / f".final_adapter.tmp-{os.getpid()}"
        model.save_pretrained(temporary_adapter, safe_serialization=True)
        os.replace(temporary_adapter, final_adapter)
    summary = {
        "complete": True,
        "global_step": global_step,
        "planned_optimizer_steps": total_steps,
        "epochs_visited": last_epoch + 1,
        "max_steps_limited": args.max_steps is not None
        and args.max_steps < planned_steps,
        "checkpoint_selection": "Compare checkpoints with development-only online rollouts; never tune on test tasks. Dev loss alone is not task success",
        "epoch_eval_metrics": epoch_metrics,
        "initial_eval_loss": initial_eval_loss,
        "invocation_initial_eval_loss": invocation_initial_eval_loss,
        "final_eval_loss": final_eval_loss,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "elapsed_seconds_scope": "Current invocation from its initial evaluation; model loading and previous invocations excluded",
        "checkpoint_lineage_elapsed_seconds": round(
            previous_elapsed + time.monotonic() - started, 3
        ),
        "checkpoint_lineage_elapsed_scope": "Intervals through restored checkpoints plus current invocation; model loading, interrupted uncheckpointed work and checkpoint writes after the saved timer excluded. Use Slurm accounting for total allocated cost",
        "resumed_from_checkpoint": checkpoint.name if checkpoint is not None else None,
        "peak_memory_gib": round(
            max(previous_peak, torch.cuda.max_memory_allocated() / 2**30), 3
        ),
        "train_rows": len(train_data),
        "dev_rows": len(dev_data),
        "max_seq_length": args.max_seq_length,
        "adapter": "final_adapter",
    }
    atomic_json(completed_summary, summary)
    print(json.dumps(summary, indent=2))


def _restore_handlers(handlers: dict[int, Any]) -> tuple[BaseException, ...]:
    errors: list[BaseException] = []
    for signum, handler in handlers.items():
        try:
            signal.signal(signum, handler)
        except BaseException as error:
            errors.append(error)
    return tuple(errors)


def run_original_sft(
    args: argparse.Namespace,
    all_train: list[dict[str, Any]],
    all_dev: list[dict[str, Any]],
    contract: dict[str, Any],
    control: OperationControl,
) -> None:
    if threading.current_thread() is not threading.main_thread():
        raise ValueError(
            "Original SFT signal ownership requires a supervised main thread"
        )
    handlers: dict[int, Any] = {
        s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGUSR1)
    }
    try:
        _run_original_sft(args, all_train, all_dev, contract, control)
    except BaseException as primary:
        errors = _restore_handlers(handlers)
        if errors:
            raise BaseExceptionGroup(
                "Original SFT and handler cleanup failed", [primary, *errors]
            ) from primary
        raise
    else:
        errors = _restore_handlers(handlers)
        if errors:
            raise BaseExceptionGroup(
                "Original SFT handler cleanup failed", list(errors)
            )
