"""Durable tool-call journal. Unknown side effects require explicit inspection.

This records execution, not generic prompt memoization or exactly-once effects.
The caller must persist the assistant's tool calls before invoking begin().
"""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import threading
from typing import Any, Iterator

from .session import state_root, validate_session_id


class UnknownExecution(RuntimeError):
    """A previous execution may have had effects; never automatically repeat it."""


class JournalConflict(ValueError):
    """A tool ID was reused with different inputs or an illegal transition."""


class JournalCorruption(ValueError):
    """The log cannot safely be interpreted; preserve it for diagnosis."""


_locks_guard = threading.Lock()
_locks: dict[str, threading.RLock] = {}


class ExecutionJournal:
    def __init__(self, session_id: str, directory: Path | None = None):
        validate_session_id(session_id)
        directory = Path(directory) if directory is not None else state_root() / "journals"
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f"{session_id}.jsonl"
        self.lock_path = directory / f"{session_id}.lock"
        with _locks_guard:
            self._lock = _locks.setdefault(str(self.path.resolve()), threading.RLock())

    @contextmanager
    def _locked(self) -> Iterator[None]:
        with self._lock:
            with self.lock_path.open("a") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _signature(name: str, args: dict[str, Any]) -> str:
        value = json.dumps({"name": name, "args": args}, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        return hashlib.sha256(value.encode()).hexdigest()

    def _records(self) -> dict[str, dict[str, Any]]:
        records: dict[str, dict[str, Any]] = {}
        if not self.path.exists():
            return records
        try:
            with self.path.open(encoding="utf-8") as stream:
                for number, line in enumerate(stream, 1):
                    if not line.endswith("\n"):
                        raise ValueError(f"partial line {number}")
                    item = json.loads(line)
                    call_id, state = item["call_id"], item["state"]
                    if not isinstance(call_id, str) or not call_id:
                        raise ValueError(f"invalid call ID at line {number}")
                    prior = records.get(call_id)
                    if state == "started":
                        if prior or item["args_hash"] != self._signature(item["name"], item["args"]):
                            raise ValueError(f"invalid start at line {number}")
                    elif state in {"completed", "unknown"}:
                        if prior is None or prior["state"] != "started":
                            raise ValueError(f"invalid transition at line {number}")
                        if state == "completed" and not isinstance(item["result"], str):
                            raise ValueError(f"invalid result at line {number}")
                    elif state == "acknowledged":
                        if prior is None or prior["state"] not in {"started", "unknown"}:
                            raise ValueError(f"invalid acknowledgement at line {number}")
                        if not isinstance(item.get("note"), str) or not item["note"].strip():
                            raise ValueError(f"missing acknowledgement note at line {number}")
                    else:
                        raise ValueError(f"invalid state at line {number}")
                    records[call_id] = {**(prior or {}), **item}
        except (ValueError, KeyError, TypeError, UnicodeError) as exc:
            raise JournalCorruption(f"Cannot restore execution journal {self.path}: {exc}") from exc
        return records

    def _append(self, record: dict[str, Any]) -> None:
        # fsync before returning: begin must be durable before side effects start.
        encoded = json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n"
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        directory_fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def lookup(self, call_id: str) -> dict[str, Any] | None:
        with self._locked():
            record = self._records().get(call_id)
            if record and record["state"] == "started":
                # A process restart cannot establish whether the effect happened.
                return {**record, "state": "unknown", "reason": "Execution started without a durable result"}
            return record

    def begin(self, call_id: str, name: str, args: dict[str, Any]) -> str | None:
        if not isinstance(call_id, str) or not call_id:
            raise ValueError("A stable nonempty tool call ID is required")
        signature = self._signature(name, args)
        with self._locked():
            prior = self._records().get(call_id)
            if prior:
                if prior["args_hash"] != signature:
                    raise JournalConflict(f"Tool call {call_id} was reused with different inputs")
                if prior["state"] == "completed":
                    return prior["result"]
                raise UnknownExecution(
                    f"Tool call {call_id} ({name}) has an unknown result. "
                    "Inspect its effects before issuing any replacement operation."
                )
            self._append({"call_id": call_id, "state": "started", "name": name,
                          "args": args, "args_hash": signature})
            return None

    def complete(self, call_id: str, result: str) -> None:
        if not isinstance(result, str):
            raise TypeError("Tool results must be strings")
        with self._locked():
            prior = self._records().get(call_id)
            if prior and prior["state"] == "completed" and prior["result"] == result:
                return
            if not prior or prior["state"] != "started":
                raise JournalConflict(f"Cannot complete tool call {call_id}")
            self._append({"call_id": call_id, "state": "completed", "result": result})

    def mark_unknown(self, call_id: str, reason: str) -> None:
        with self._locked():
            prior = self._records().get(call_id)
            if prior and prior["state"] == "unknown":
                return
            if not prior or prior["state"] != "started":
                raise JournalConflict(f"Cannot mark tool call {call_id} unknown")
            self._append({"call_id": call_id, "state": "unknown", "reason": reason})

    def unresolved(self) -> list[dict[str, Any]]:
        with self._locked():
            return [
                {**item, "state": "unknown"}
                for item in self._records().values()
                if item["state"] in {"started", "unknown"}
            ]

    def acknowledge_unknown(self, call_id: str, note: str) -> None:
        """Record explicit user inspection; never make the original call replayable."""
        if not isinstance(note, str) or not note.strip():
            raise ValueError("Acknowledgement requires a nonempty inspection note")
        with self._locked():
            prior = self._records().get(call_id)
            if not prior or prior["state"] not in {"started", "unknown"}:
                raise JournalConflict(f"No unresolved execution for {call_id}")
            self._append({"call_id": call_id, "state": "acknowledged", "note": note})
