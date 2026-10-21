"""Session management — JSON file persistence for conversation history."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

def state_root() -> Path:
    """Keep large state off HOME when an ATUIN location is configured."""
    if os.environ.get("MINI_CLAUDE_STATE_DIR"):
        return Path(os.environ["MINI_CLAUDE_STATE_DIR"]).expanduser()
    if os.environ.get("ATUIN"):
        return Path(os.environ["ATUIN"]) / "coding-agent-demo-state"
    return Path.home() / ".mini-claude"


SESSION_DIR = state_root() / "sessions"


def state_dir() -> Path:
    return state_root()


class SessionCorruption(ValueError):
    """An existing session cannot safely be restored."""


def validate_session_id(session_id: str) -> str:
    if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", session_id):
        raise ValueError("Invalid session ID; use 1–128 letters, digits, hyphens or underscores")
    return session_id


def _ensure_dir() -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)


def save_session(session_id: str, data: dict[str, Any]) -> None:
    validate_session_id(session_id)
    _ensure_dir()
    # Same-directory replace prevents a crash exposing a half-written JSON file.
    payload = json.dumps(data, indent=2, default=str)
    fd, name = tempfile.mkstemp(prefix=f".{session_id}.", suffix=".tmp", dir=SESSION_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, SESSION_DIR / f"{session_id}.json")
        dir_fd = os.open(SESSION_DIR, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def load_session(session_id: str) -> dict[str, Any] | None:
    validate_session_id(session_id)
    path = SESSION_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not any(
            isinstance(data.get(key), list)
            for key in ("messages", "openaiMessages", "anthropicMessages")
        ):
            raise ValueError("Expected a session object with a backend messages list")
        return data
    except (ValueError, UnicodeError) as exc:
        raise SessionCorruption(f"Cannot restore {path}: {exc}. Original file was preserved.") from exc


def list_sessions() -> list[dict[str, Any]]:
    _ensure_dir()
    results = []
    for f in SESSION_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            if "metadata" in data:
                results.append(data["metadata"])
        except Exception:
            pass
    return results


def get_latest_session_id() -> str | None:
    sessions = list_sessions()
    if not sessions:
        return None
    sessions.sort(key=lambda s: s.get("startTime", ""), reverse=True)
    return sessions[0].get("id")
