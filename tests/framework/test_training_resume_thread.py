"""Actual unchanged run-contract resume and shared library caller boundaries."""

import argparse
from dataclasses import replace
from pathlib import Path
import threading
from typing import Any
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.training import torch_sft
from lab_generate_skill.bootstrap.training import training_dependencies
from lab_generate_skill.application.train_sft import train_sft
from lab_generate_skill.domain.training import TrainingPlan
from training_entry_fixtures import (
    training_case,
    TrainingCase,
    UnitTrainingAuthority,
    UnitTrainingRuntime,
)
from test_training_entry import install_contract_only_leaf
from test_training_engine_boundaries import UnitControl


def test_explicit_same_original_resume_reuses_completed_fact_without_another_model(
    training_case: TrainingCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = training_case
    calls = install_contract_only_leaf(c, monkeypatch)
    a, r = UnitTrainingAuthority(), UnitTrainingRuntime()
    deps = training_dependencies(
        c.export.deps,
        authority=a,
        runtime=r,
        output_root=c.root / "explicit-resume",
        clock=SystemClock(),
    )
    plan = c.plan("explicit-resume")
    first = train_sft(plan, deps)
    reading = c.plan("explicit-resume-read")
    resumed = TrainingPlan.model_validate(
        {
            **reading.model_dump(),
            "training_id": plan.training_id,
            "spec": plan.spec.model_copy(update={"resume": True}),
        }
    )
    second = train_sft(resumed, deps)
    assert first.result == second.result and first.plan_ref != second.plan_ref
    assert len(calls) == 1 and a.calls == [
        "verify",
        "verify_result",
        "verify",
        "verify_result",
    ]


def test_maximum_original_training_id_has_bounded_owned_output_name(
    training_case: TrainingCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = training_case
    calls = install_contract_only_leaf(c, monkeypatch)
    a, r = UnitTrainingAuthority(), UnitTrainingRuntime()
    deps = training_dependencies(
        c.export.deps,
        authority=a,
        runtime=r,
        output_root=c.root / "max-id",
        clock=SystemClock(),
    )
    original = c.plan("max-id")
    plan = TrainingPlan.model_validate(
        {**original.model_dump(), "training_id": "unit-sft-" + "A" * 247}
    )
    receipt = train_sft(plan, deps)
    assert (
        receipt.result.training_id == plan.training_id and len(plan.training_id) == 256
    )
    output = calls[0][0].output_dir
    assert isinstance(output, Path) and len(output.name) == 68
    assert (
        output.parent == c.root / "max-id"
        and calls[0][3]["training_id"] == plan.training_id
    )


def test_non_main_thread_is_rejected_before_original_model_leaf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    errors: list[BaseException] = []

    def core(*args: Any, **kwargs: Any) -> None:
        calls.append("unexpected model")

    monkeypatch.setattr(torch_sft, "_run_original_sft", core)

    def run() -> None:
        try:
            torch_sft.run_original_sft(argparse.Namespace(), [], [], {}, UnitControl())
        except BaseException as error:
            errors.append(error)

    worker = threading.Thread(target=run)
    worker.start()
    worker.join(5)
    assert not worker.is_alive() and len(errors) == 1
    assert isinstance(errors[0], ValueError) and "supervised main thread" in str(
        errors[0]
    )
    assert calls == []
