"""Training contract, failed admission, uncertain publication and explicit resume."""

from dataclasses import replace
from datetime import datetime, timezone, timedelta
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.training.sft import TrainingBackendUnconfirmed
from lab_generate_skill.application.train_sft import train_sft, TrainingUnconfirmed
from lab_generate_skill.bootstrap.training import training_dependencies
from lab_generate_skill.domain.training import (
    TrainingPlan,
    TrainingSpec,
    TrainingRunResult,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OperationStopped
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_run_journal import CancelSwitch
from test_export_targets_boundaries import LostAckStore
from training_entry_fixtures import (
    training_case,
    TrainingCase,
    UnitTrainingAuthority,
    UnitTrainingRuntime,
)
from test_training_entry import install_contract_only_leaf


@pytest.mark.parametrize(
    "change",
    [
        {"max_seq_length": 0},
        {"max_seq_length": 16385},
        {"max_seq_length": True},
        {"epochs": "3"},
        {"lora_r": -1},
        {"lora_dropout": 1.0},
        {"learning_rate": float("nan")},
        {"warmup_ratio": float("inf")},
        {"max_steps": 0},
        {"train_limit": -1},
        {"resume": 1},
        {"unknown": True},
    ],
)
def test_training_spec_rejects_wrong_types_nonfinite_and_unqualified_expansion(
    change: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        TrainingSpec.model_validate(change)


def test_training_plan_rejects_fixture_or_inspection_and_wrong_phase_ref(
    training_case: TrainingCase,
) -> None:
    plan = training_case.plan("bad-plan")
    for dataset in (
        plan.dataset.model_copy(update={"purpose": "inspect"}),
        plan.dataset.model_copy(
            update={"purpose": "inspect", "expected_kind": "engineering_fixture"}
        ),
    ):
        with pytest.raises(ValidationError):
            TrainingPlan.model_validate({**plan.model_dump(), "dataset": dataset})
    with pytest.raises(ValidationError):
        TrainingPlan.model_validate({**plan.model_dump(), "cleanup_seconds": 0})
    with pytest.raises(ValidationError):
        TrainingPlan.model_validate(
            {**plan.model_dump(), "phase_authorization_ref": plan.training_release_ref}
        )
    longest = TrainingPlan.model_validate(
        {**plan.model_dump(), "training_id": "A" * 256}
    )
    cleanup = longest.cleanup("result", datetime.now(timezone.utc))
    assert len(cleanup.operation_id) < 256 and cleanup.mode == "cleanup"
    assert cleanup.parent_operation_id == longest.dataset.operation.operation_id


@pytest.mark.parametrize("mode", ["denied", "cancelled", "expired"])
def test_no_phase_permission_or_live_control_stops_before_model(
    training_case: TrainingCase, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    c = training_case
    calls = install_contract_only_leaf(c, monkeypatch)
    a, r = UnitTrainingAuthority(), UnitTrainingRuntime()
    plan = c.plan("stop-" + mode)
    if mode == "denied":
        a.denied = True
    elif mode == "cancelled":

        def cancelled(*args: Any, **kwargs: Any) -> None:
            raise OperationStopped("CANCELLED", plan.dataset.operation.operation_id)

        monkeypatch.setattr(a, "verify", cancelled)
    else:
        op = plan.dataset.operation.model_copy(
            update={"deadline": datetime.now(timezone.utc) - timedelta(seconds=1)}
        )
        plan = TrainingPlan.model_validate(
            {
                **plan.model_dump(),
                "dataset": plan.dataset.model_copy(update={"operation": op}),
            }
        )
    deps = training_dependencies(
        c.export.deps,
        authority=a,
        runtime=r,
        output_root=c.root / ("stop-" + mode),
        clock=SystemClock(),
    )
    with pytest.raises(TrainingUnconfirmed) as caught:
        train_sft(plan, deps)
    assert caught.value.retained == () and caught.value.result is None
    assert calls == [] and r.calls == []
    assert isinstance(
        caught.value.primary, PermissionError if mode == "denied" else OperationStopped
    )


def test_changed_loaded_view_or_empty_data_cannot_reach_tokenizer(
    training_case: TrainingCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = training_case
    calls = install_contract_only_leaf(c, monkeypatch)
    a, r = UnitTrainingAuthority(), UnitTrainingRuntime()
    deps = training_dependencies(
        c.export.deps,
        authority=a,
        runtime=r,
        output_root=c.root / "invalid-view",
        clock=SystemClock(),
    )
    for name, data in (
        ("empty", replace(c.data, examples=())),
        ("inspect", replace(c.data, purpose="inspect")),
        (
            "changed-target",
            replace(
                c.data,
                examples=(
                    c.data.examples[0].model_copy(
                        update={"goal_group_id": "different-group"}
                    ),
                    c.data.examples[1],
                ),
            ),
        ),
    ):
        monkeypatch.setattr(
            "lab_generate_skill.application.train_sft.load_dataset", lambda p, d: data
        )
        with pytest.raises(TrainingUnconfirmed) as caught:
            train_sft(c.plan("bad-view-" + name), deps)
        assert isinstance(caught.value.primary, EvidenceIntegrityError)
        assert caught.value.retained == ()
    assert a.calls == r.calls == calls == []


def test_runtime_failure_preserves_primary_cleanup_error_and_known_plan(
    training_case: TrainingCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = training_case
    calls = install_contract_only_leaf(c, monkeypatch)
    a, r = UnitTrainingAuthority(), UnitTrainingRuntime()
    primary = OSError("unit runtime ownership rejected")
    cleanup = RuntimeError("unit original cleanup incomplete")
    r.error = primary

    def bad_abort(*args: Any, **kwargs: Any) -> None:
        raise cleanup

    monkeypatch.setattr(r, "abort", bad_abort)
    deps = training_dependencies(
        c.export.deps,
        authority=a,
        runtime=r,
        output_root=c.root / "runtime-failure",
        clock=SystemClock(),
    )
    with pytest.raises(TrainingUnconfirmed) as caught:
        train_sft(c.plan("runtime-failure"), deps)
    backend = caught.value.primary
    assert (
        isinstance(backend, TrainingBackendUnconfirmed) and backend.primary is primary
    )
    assert backend.cleanup_errors == (cleanup,)
    assert (
        len(caught.value.retained) == 1 and caught.value.result is None and calls == []
    )


@pytest.mark.parametrize("stage", [1, 2, 3])
def test_committed_training_metadata_with_lost_ack_never_repeats_model(
    training_case: TrainingCase, monkeypatch: pytest.MonkeyPatch, stage: int
) -> None:
    c = training_case
    calls = install_contract_only_leaf(c, monkeypatch)
    a, r = UnitTrainingAuthority(), UnitTrainingRuntime()
    store = LostAckStore(c.export.deps.evidence, stage)
    dataset = replace(c.export.deps, evidence=store)
    deps = training_dependencies(
        dataset,
        authority=a,
        runtime=r,
        output_root=c.root / ("lost-" + str(stage)),
        clock=SystemClock(),
    )
    with pytest.raises(TrainingUnconfirmed) as caught:
        train_sft(c.plan("lost-ack-" + str(stage)), deps)
    assert caught.value.primary is store.error
    assert caught.value.retained == tuple(store.committed)
    assert len(caught.value.retained) == stage and len(calls) == (
        0 if stage == 1 else 1
    )
    assert (caught.value.result is None) == (stage == 1)


class UnitClock:
    def __init__(self) -> None:
        self.now = datetime.now(timezone.utc)
        self.elapsed = 0.0

    def utcnow(self) -> datetime:
        return self.now

    def monotonic(self) -> float:
        return self.elapsed

    def sleep(self, seconds: float) -> None:
        self.elapsed += seconds
        self.now += timedelta(seconds=seconds)


def test_known_result_after_original_expiry_uses_only_bounded_cleanup(
    training_case: TrainingCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = training_case
    calls = install_contract_only_leaf(c, monkeypatch)
    clock = UnitClock()
    control = OperationGuards(clock, CancelSwitch())
    old_core = import_module_core()

    def expires(*args: Any, **kwargs: Any) -> None:
        old_core(*args, **kwargs)
        clock.sleep(600)

    monkeypatch.setattr(
        "lab_generate_skill.adapters.training.torch_sft.run_original_sft", expires
    )
    a, r = UnitTrainingAuthority(), UnitTrainingRuntime()
    deps = training_dependencies(
        replace(c.export.deps, controls=control),
        authority=a,
        runtime=r,
        output_root=c.root / "late-result",
        clock=clock,
    )
    plan = c.plan("late-result")
    result = train_sft(plan, deps)
    assert result.result.status == "completed" and len(calls) == 1
    with pytest.raises(OperationStopped):
        control.bind(plan.dataset.operation).checkpoint()
    assert r.calls == ["verify", "execute", "finish"] and a.calls == [
        "verify",
        "verify_result",
    ]


def import_module_core() -> Any:
    from importlib import import_module

    return import_module(
        "lab_generate_skill.adapters.training.torch_sft"
    ).run_original_sft
