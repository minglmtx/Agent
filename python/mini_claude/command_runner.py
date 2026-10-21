"""Bounded Linux shell execution, streaming output and process-group cancellation.

Callbacks run on the caller's thread (normally an asyncio worker thread). Log
files contain command output, not the command/environment, and have mode 0600.
They may still contain secrets printed by a command; treat them as private.
"""
from __future__ import annotations

import codecs
from dataclasses import dataclass
import math
import os
from pathlib import Path
import selectors
import signal
import subprocess
import threading
import time
from typing import Callable
import uuid

from .session import state_root

OutputCallback = Callable[[str, str], None]
_active: set[threading.Event] = set()
_active_lock = threading.Lock()


@dataclass(frozen=True)
class CommandResult:
    status: str
    exit_code: int | None
    stdout: str
    stderr: str
    duration_s: float
    log_path: str | None
    output_truncated: bool = False
    log_truncated: bool = False

    def render(self) -> str:
        lines = [f"Command status: {self.status}; exit code: {self.exit_code}; duration: {self.duration_s:.2f}s"]
        if self.stdout:
            lines.append(f"Stdout:\n{self.stdout}")
        if self.stderr:
            lines.append(f"Stderr:\n{self.stderr}")
        if not self.stdout and not self.stderr:
            lines.append("(no output)")
        if self.output_truncated:
            lines.append("[Tool output truncated; inspect the private log for more output.]")
        if self.log_path:
            lines.append(f"Output log: {self.log_path}")
        if self.log_truncated:
            lines.append("[Log size limit reached; remaining output was drained but not stored.]")
        return "\n".join(lines)


def cancel_all_commands() -> int:
    """Request cancellation of currently registered commands, without blocking."""
    with _active_lock:
        events = tuple(_active)
    for event in events:
        event.set()
    return len(events)


def _signal_group(proc: subprocess.Popen, sig: int) -> None:
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        pass


def run_command(
    command: str,
    timeout_s: float = 30,
    *,
    on_output: OutputCallback | None = None,
    cancel_event: threading.Event | None = None,
    log_dir: str | Path | None = None,
    max_output_bytes: int = 32_000,
    max_log_bytes: int = 2_000_000,
    terminate_grace_s: float = 0.3,
) -> CommandResult:
    """Execute with finite timeout; TERM then KILL the entire Linux process group.

    Output and callbacks share a memory/UI budget; disk logs have a separate cap.
    Detached descendants that create a new session are outside this guarantee.
    """
    if os.name != "posix":
        raise RuntimeError("This demo command runner supports Linux/POSIX only")
    if not isinstance(command, str) or not command.strip():
        raise ValueError("command must be a nonempty string")
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("timeout must be finite and positive")
    if min(max_output_bytes, max_log_bytes) < 1 or terminate_grace_s < 0:
        raise ValueError("output limits must be positive and grace must be nonnegative")
    event = cancel_event if cancel_event is not None else threading.Event()
    started = time.monotonic()
    default_root = state_root()
    directory = Path(log_dir) if log_dir is not None else default_root / "command-logs"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_path = directory / f"{uuid.uuid4().hex}.log"
    output: dict[str, list[str]] = {"stdout": [], "stderr": []}
    decoders = {key: codecs.getincrementaldecoder("utf-8")("replace") for key in output}
    remaining_output, remaining_log = max_output_bytes, max_log_bytes
    output_truncated = log_truncated = False
    status = "completed"
    proc: subprocess.Popen | None = None
    stop_at: float | None = None
    killed = False
    selector = selectors.DefaultSelector()
    with _active_lock:
        _active.add(event)
    try:
        with os.fdopen(os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as log:
            def consume(name: str, chunk: bytes, final: bool = False) -> None:
                nonlocal remaining_output, remaining_log, output_truncated, log_truncated
                if chunk:
                    record = f"[{name}] ".encode() + chunk
                    kept_log = record[:remaining_log]
                    log.write(kept_log)
                    log.flush()
                    remaining_log -= len(kept_log)
                    log_truncated |= len(kept_log) < len(record)
                kept = chunk[:remaining_output]
                remaining_output -= len(kept)
                output_truncated |= len(kept) < len(chunk)
                text = decoders[name].decode(kept, final=final)
                if text:
                    output[name].append(text)
                    if on_output is not None:
                        # UI failures must not interrupt process cleanup/output draining.
                        try:
                            on_output(name, text)
                        except Exception:
                            pass

            if event.is_set():
                status = "cancelled"
            else:
                proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, start_new_session=True)
                for name, pipe in (("stdout", proc.stdout), ("stderr", proc.stderr)):
                    os.set_blocking(pipe.fileno(), False)
                    selector.register(pipe, selectors.EVENT_READ, name)
                while selector.get_map() or proc.poll() is None or (stop_at is not None and not killed):
                    now = time.monotonic()
                    if stop_at is None and (event.is_set() or now - started >= timeout_s):
                        status = "cancelled" if event.is_set() else "timed_out"
                        stop_at = now
                        _signal_group(proc, signal.SIGTERM)
                    if stop_at is not None and not killed and now - stop_at >= terminate_grace_s:
                        _signal_group(proc, signal.SIGKILL)
                        killed = True
                    # Do not hang on pipe handles inherited by detached descendants.
                    if stop_at is not None and now - stop_at > terminate_grace_s + 1:
                        break
                    for key, _ in selector.select(timeout=0.05):
                        try:
                            chunk = os.read(key.fileobj.fileno(), 8192)
                        except BlockingIOError:
                            continue
                        if chunk:
                            consume(key.data, chunk)
                        else:
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                            consume(key.data, b"", final=True)
                if status == "completed" and proc.wait() != 0:
                    status = "failed"
    finally:
        if proc is not None:
            # The tool owns its process group for its entire lifetime. A shell
            # may exit after spawning a background child with redirected output;
            # cleaning even after parent exit avoids leaking that child.
            _signal_group(proc, signal.SIGKILL)
            proc.wait()
            for pipe in (proc.stdout, proc.stderr):
                if pipe and not pipe.closed:
                    pipe.close()
        selector.close()
        with _active_lock:
            _active.discard(event)
    return CommandResult(status, proc.returncode if proc else None,
                         "".join(output["stdout"]), "".join(output["stderr"]),
                         time.monotonic() - started, str(log_path),
                         output_truncated, log_truncated)
