"""Nonblocking lifetime lease for one local session process (Linux)."""

from contextlib import contextmanager
import fcntl
import os
from typing import Iterator

from .session import state_dir, validate_session_id


class SessionBusy(RuntimeError):
    pass


@contextmanager
def session_lease(session_id: str) -> Iterator[None]:
    validate_session_id(session_id)
    directory = state_dir() / "locks"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{session_id}.lock"
    with path.open("a+") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SessionBusy(f"Session {session_id} is already in use by another process") from exc
        try:
            stream.seek(0)
            stream.truncate()
            stream.write(str(os.getpid()) + "\n")
            stream.flush()
            yield
        finally:
            # Leave the lock file in place. Unlinking creates an inode race.
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
