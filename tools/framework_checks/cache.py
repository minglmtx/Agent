"""Bounded cache locking and byte inventories for development artifacts."""

from collections.abc import Iterator
from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
import time


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_files(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ValueError(f"Cache payload contains a symlink: {path}")
        if path.is_file():
            result[str(path.relative_to(root))] = file_digest(path)
    return result


@contextmanager
def cache_lock(path: Path, *, timeout: float = 90) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    end = time.monotonic() + timeout
    with path.open("a+b") as stream:
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= end:
                    raise TimeoutError(f"Development cache lock timed out: {path}")
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)
