"""Append bounded phase metadata to one source-local stream; never native values."""
from contextlib import contextmanager
import json
from pathlib import Path
import time
import uuid


@contextmanager
def phase(directory, name):
    if not isinstance(name, str) or not name or len(name) > 80 or not all(c.isalnum() or c in "_-" for c in name):
        raise ValueError("Static phase identifier required")
    path = Path(directory) / "phase-timing.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    began = time.monotonic()
    identifier = uuid.uuid4().hex
    def event(status, error=None):
        row = {"phase": name, "id": identifier, "status": status,
               "monotonic": time.monotonic(), "seconds": time.monotonic() - began}
        if error is not None:
            row["error_type"] = type(error).__name__
        with path.open("a") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    event("started")
    try:
        yield
    except BaseException as error:
        try:
            event("failed", error)
        except OSError:
            # Preserve the original runtime error if diagnostic storage also fails.
            pass
        raise
    else:
        event("complete")
