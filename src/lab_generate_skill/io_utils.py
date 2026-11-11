from __future__ import annotations

import json
import gzip
import os
import tempfile
from collections.abc import Iterable, Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any


def iter_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Expected JSON object at {path}:{line_number}")
            yield value


@lru_cache(maxsize=None)
def cached_jsonl(path: str) -> tuple[dict[str, Any], ...]:
    """Read a trusted JSONL file once per process and retain its parsed content."""

    return tuple(iter_jsonl(path))


@lru_cache(maxsize=None)
def cached_text(path: str) -> str:
    """Read a trusted text file once per process and retain its content."""

    with Path(path).open("r", encoding="utf-8") as handle:
        return handle.read()


def append_jsonl(path: str | Path, records: Iterable[dict[str, Any]], *, durable: bool = True) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
        handle.flush()
        if durable:
            os.fsync(handle.fileno())


def json_text(value: Any, *, indent: int | None = 2, compact_above: int = 262144) -> str:
    """Keep small reports readable and large machine evidence compact.

    Only insignificant JSON whitespace changes; strings, fields and ordering
    remain intact. Existing evidence files and their recorded hashes are never
    rewritten. Callers that require pretty output can use compact_above=0.
    """
    compact = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if indent is None or (compact_above and len(compact) >= compact_above):
        return compact + "\n"
    return json.dumps(value, ensure_ascii=False, indent=indent) + "\n"


def atomic_write_json(path: str | Path, value: Any, *, indent: int | None = 2) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            handle.write(json_text(value, indent=indent))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def atomic_save_numpy(path: str | Path, array: Any) -> None:
    import numpy as np

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".npy", dir=destination.parent
    )
    os.close(file_descriptor)
    try:
        np.save(temporary_name, array)
        os.replace(temporary_name, destination)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def read_json(path: str | Path) -> Any:
    """Load complete JSON, optionally gzip-compressed without field changes.

    Compression changes only storage. Admission and source-binding validation
    still receive the entire original object and must run after this read.
    """
    source = Path(path)
    opener = gzip.open if source.name.endswith(".json.gz") else open
    with opener(source, "rt", encoding="utf-8") as handle:
        value = json.load(handle)
    from .evidence_store import resolve
    return resolve(source, value)
