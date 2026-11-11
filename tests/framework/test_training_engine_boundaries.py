"""Original checkpoint/file contracts and library-owned signal restoration."""

import argparse
from importlib import import_module
from pathlib import Path
import signal
from typing import Any
import pytest
from lab_generate_skill.adapters.training.files import (
    check_run_contract,
    latest_checkpoint,
    atomic_json,
)
from lab_generate_skill.adapters.training import torch_sft


class UnitControl:
    def checkpoint(self) -> float:
        return 30.0

    def wait(self, seconds: float) -> None:
        assert seconds >= 0


@pytest.mark.parametrize("raises", [False, True])
def test_shared_original_engine_restores_callers_handlers_after_return_or_error(
    monkeypatch: pytest.MonkeyPatch, raises: bool
) -> None:
    before = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGUSR1)}
    primary = OSError("unit original training step failed")
    calls: list[str] = []

    def handler(signum: int, frame: Any) -> None:
        pass

    def core(*args: Any, **kwargs: Any) -> None:
        calls.append("core")
        signal.signal(signal.SIGTERM, handler)
        signal.signal(signal.SIGUSR1, handler)
        if raises:
            raise primary

    monkeypatch.setattr(torch_sft, "_run_original_sft", core)
    if raises:
        with pytest.raises(OSError) as caught:
            torch_sft.run_original_sft(argparse.Namespace(), [], [], {}, UnitControl())
        assert caught.value is primary
    else:
        torch_sft.run_original_sft(argparse.Namespace(), [], [], {}, UnitControl())
    assert calls == ["core"]
    assert {s: signal.getsignal(s) for s in before} == before


def test_handler_restore_failure_preserves_first_error_and_attempts_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = RuntimeError("unit optimizer failure")
    cleanup = OSError("unit handler restore refused")
    restored: list[int] = []

    def core(*args: Any, **kwargs: Any) -> None:
        raise primary

    def restore(signum: int, handler: Any) -> None:
        restored.append(signum)
        if signum == signal.SIGTERM:
            raise cleanup

    monkeypatch.setattr(torch_sft, "_run_original_sft", core)
    monkeypatch.setattr(signal, "signal", restore)
    with pytest.raises(BaseExceptionGroup) as caught:
        torch_sft.run_original_sft(argparse.Namespace(), [], [], {}, UnitControl())
    assert caught.value.exceptions == (primary, cleanup)
    assert restored == [signal.SIGTERM, signal.SIGUSR1]


def test_original_checkpoint_and_manifest_rules_do_not_create_empty_resume(
    tmp_path: Path,
) -> None:
    root = tmp_path / "original"
    check_run_contract(root, {"unit-original": 1}, False)
    with pytest.raises(ValueError, match="Existing run requires"):
        check_run_contract(root, {"unit-original": 1}, False)
    check_run_contract(root, {"unit-original": 1}, True)
    with pytest.raises(ValueError, match="changed"):
        check_run_contract(root, {"unit-original": 2}, True)
    for step in (1, 3):
        atomic_json(
            root / f"checkpoint-{step:06d}" / "complete.json", {"unit-checkpoint": True}
        )
    (root / "checkpoint-000004").mkdir()
    (root / "checkpoint-invalid").mkdir()
    assert latest_checkpoint(root) == root / "checkpoint-000003"
    partial = tmp_path / "nonempty-no-manifest"
    partial.mkdir()
    (partial / "original-partial-output").write_text("preserve")
    with pytest.raises(ValueError, match="Nonempty output"):
        check_run_contract(partial, {"unit-original": 1}, True)
    assert (partial / "original-partial-output").read_text() == "preserve"
    root_module = import_module("lab_generate_skill.sft_train")
    assert root_module.collate_examples is torch_sft.collate_examples
    assert root_module.latest_checkpoint is latest_checkpoint
