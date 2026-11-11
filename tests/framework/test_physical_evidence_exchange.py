"""Original reply capture is one-shot, including thrown/unknown first calls."""

from pathlib import Path
import pytest
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from lab_generate_skill.adapters.storage.physical_exchange import (
    PhysicalEvidenceExchange,
)
from lab_generate_skill.adapters.storage import evidence_worker
from lab_generate_skill.adapters.storage.worker_protocol import encode_command
from evidence_worker_fixtures import command


def test_capture_keeps_exact_reply_and_cannot_execute_twice(tmp_path: Path) -> None:
    raw = encode_command(command(tmp_path), b"evidence")
    physical = PhysicalEvidenceExchange(raw)
    result = physical.execute(raw)
    assert physical.raw == raw and physical.reply == result
    with pytest.raises(DispatchAlreadyCommitted):
        physical.execute(raw)


def test_wrong_command_has_no_effect_and_first_failure_is_not_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = encode_command(command(tmp_path), b"evidence")
    physical = PhysicalEvidenceExchange(raw)
    with pytest.raises(OwnershipConflict):
        physical.execute(raw + b"x")
    assert list(tmp_path.iterdir()) == []
    calls = []

    def fail(raw: bytes) -> bytes:
        calls.append(raw)
        raise OSError("unknown original operation")

    monkeypatch.setattr(evidence_worker, "exchange", fail)
    with pytest.raises(OSError):
        physical.execute(raw)
    with pytest.raises(DispatchAlreadyCommitted):
        physical.execute(raw)
    assert calls == [raw] and physical.reply is None


def test_nested_cleanup_group_retains_first_observation_and_handles_cause_cycle() -> (
    None
):
    from lab_generate_skill.adapters.storage.registered_exchange_result import (
        RegisteredExchangeObservation,
        RegisteredExchangeFailure,
        retained_registered_exchange,
    )

    known = RegisteredExchangeObservation("outcome", None, b"actual reply", None)
    first = RegisteredExchangeFailure(known)
    outer = RuntimeError("outer")
    outer.__cause__ = ExceptionGroup("both", [first, OSError("close")])
    assert retained_registered_exchange(outer) is known
    cycle = RuntimeError("cycle")
    cycle.__cause__ = cycle
    assert retained_registered_exchange(cycle) is None
    interrupted = KeyboardInterrupt()
    interrupted.registered_exchange = known  # type: ignore[attr-defined]
    assert (
        retained_registered_exchange(
            BaseExceptionGroup("stop", [interrupted, OSError("close")])
        )
        is known
    )
