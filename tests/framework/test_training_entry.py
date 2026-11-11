"""Original consumer gate and shared trainer dispatch, zero actual parameter training."""

from dataclasses import replace
from importlib import import_module
from typing import Any
import pytest
from lab_generate_skill.application.train_sft import (
    train_sft,
    TrainingDeps,
    TrainingUnconfirmed,
)
from lab_generate_skill.adapters.training.files import check_run_contract, atomic_json
from lab_generate_skill.adapters.training.sft import TrainingBackendUnconfirmed
from lab_generate_skill.bootstrap.training import training_dependencies
from lab_generate_skill.bootstrap.training_entry import main
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.domain.export import DatasetLoadPlan
from lab_generate_skill.domain.training import TrainingPlan, TrainingSpec
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from training_entry_fixtures import (
    training_case,
    TrainingCase,
    UnitTrainingAuthority,
    UnitTrainingRuntime,
)


def install_contract_only_leaf(
    c: TrainingCase, monkeypatch: pytest.MonkeyPatch
) -> list[Any]:
    calls: list[Any] = []

    def core(args: Any, train: Any, dev: Any, contract: Any, control: Any) -> None:
        control.checkpoint()
        check_run_contract(args.output_dir, contract, args.resume)
        if (args.output_dir / "training_summary.json").exists():
            return
        calls.append((args, train, dev, contract))
        atomic_json(
            args.output_dir / "training_summary.json",
            {"unit_contract_only": True, "complete": True},
        )

    monkeypatch.setattr(
        "lab_generate_skill.adapters.training.torch_sft.run_original_sft", core
    )
    monkeypatch.setattr(
        "lab_generate_skill.application.train_sft.load_dataset",
        lambda plan, deps: c.data,
    )
    return calls


def test_qualified_contract_to_original_shared_adapter_and_saved_receipt_without_training(
    training_case: TrainingCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = training_case
    calls = install_contract_only_leaf(c, monkeypatch)
    authority, runtime = UnitTrainingAuthority(), UnitTrainingRuntime()
    deps = training_dependencies(
        c.export.deps,
        authority=authority,
        runtime=runtime,
        output_root=c.root / "main",
        clock=SystemClock(),
    )
    plan = c.plan("main")
    receipt = main(plan, deps)
    assert receipt.result.status == "completed" and len(calls) == 1
    args, train, valid, contract = calls[0]
    assert args.max_seq_length == 16384 and len(train) == len(valid) == 1
    assert train[0]["messages"] == [m.model_dump() for m in c.data.examples[0].messages]
    assert contract["export_receipt_ref"] == plan.dataset.export_receipt_ref.model_dump(
        mode="json"
    )
    assert authority.calls == ["verify", "verify_result"] and runtime.calls == [
        "verify",
        "execute",
        "finish",
    ]
    assert import_module("lab_generate_skill.sft_train").main is main
    assert (
        import_module("lab_generate_skill.sft_train").check_run_contract
        is check_run_contract
    )
    store = c.export.review.control.source.data.store
    assert store.read(receipt.result_ref)
    # An identical manifest is not permission to train a second time.
    with pytest.raises(TrainingUnconfirmed) as caught:
        train_sft(plan, deps)
    backend = caught.value.primary
    assert isinstance(backend, TrainingBackendUnconfirmed)
    assert isinstance(backend.primary, ValueError) and "Existing run requires" in str(
        backend.primary
    )
    assert len(calls) == 1


def test_real_engineering_export_rejected_before_training_authority_or_leaf(
    training_case: TrainingCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = training_case
    called: list[object] = []
    monkeypatch.setattr(
        "lab_generate_skill.adapters.training.torch_sft.run_original_sft",
        lambda *a: called.append(a),
    )
    plan = c.plan("real-fixture-denial")
    raw = c.export.load_plan(c.engineering_receipt_ref, "sft-fixture-denial")
    dataset = DatasetLoadPlan.model_validate(
        {**raw.model_dump(), "expected_kind": "formal", "purpose": "sft"}
    )
    plan = TrainingPlan.model_validate({**plan.model_dump(), "dataset": dataset})
    authority, runtime = UnitTrainingAuthority(), UnitTrainingRuntime()
    deps = training_dependencies(
        c.export.deps,
        authority=authority,
        runtime=runtime,
        output_root=c.root / "denied",
        clock=SystemClock(),
    )
    with pytest.raises(TrainingUnconfirmed) as caught:
        train_sft(plan, deps)
    assert isinstance(caught.value.primary, EvidenceIntegrityError)
    assert caught.value.retained == () and caught.value.phase == "original_dataset"
    assert called == authority.calls == runtime.calls == []


def test_raw_file_default_has_no_unqualified_fallback() -> None:
    with pytest.raises(ValueError, match="raw JSONL training entry is retired"):
        main()
