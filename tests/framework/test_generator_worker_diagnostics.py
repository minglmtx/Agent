"""Failure records retain exact bytes and original errors under disk faults."""

import json
from pathlib import Path
import pytest
from lab_generate_skill.adapters.processes.capture import CommandCapture
from generator_worker_diagnostics import record_failure


def capture() -> CommandCapture:
    return CommandCapture(("/worker",), None, b"reply\x00", b"model failure", False)


def test_failure_records_keep_original_and_exact_bytes(tmp_path: Path) -> None:
    error = RuntimeError("original")
    assert record_failure(tmp_path, "operation", error, capture()) is error
    assert (tmp_path / "operation-stdout.bin").read_bytes() == b"reply\x00"
    assert (tmp_path / "operation-stderr.log").read_bytes() == b"model failure"
    detail = json.loads((tmp_path / "operation-error.json").read_text())
    assert detail["error"]["type_name"] == "RuntimeError"
    assert detail["termination"] is None


@pytest.mark.parametrize("all_writes", [False, True])
def test_failed_recording_preserves_primary_and_attempts_all_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, all_writes: bool
) -> None:
    error = ValueError("original input")
    writes: list[str] = []
    original = Path.write_bytes

    def failing_write(path: Path, content: bytes) -> int:
        writes.append(path.name)
        if all_writes or path.name.endswith("stdout.bin"):
            raise OSError(28, "injected disk full")
        return original(path, content)

    monkeypatch.setattr(Path, "write_bytes", failing_write)
    result = record_failure(tmp_path, "operation", error, capture())
    assert isinstance(result, BaseExceptionGroup)
    assert result.exceptions[0] is error
    assert len(result.exceptions) == (4 if all_writes else 2)
    assert len(writes) == 3
    if not all_writes:
        assert (tmp_path / "operation-stderr.log").read_bytes() == b"model failure"
        assert (tmp_path / "operation-error.json").is_file()
