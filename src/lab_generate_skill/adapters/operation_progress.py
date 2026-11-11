"""Fixed stage markers for original long consumers; no control or permission.

Diagnostics must never replace the original work or mask its failure. Labels
are static call-site strings, without task content or private evidence bytes.
"""

from contextlib import contextmanager
from collections.abc import Iterator
import sys
import time


def _mark(label: str, event: str) -> None:
    try:
        sys.stderr.write(f"OPERATION_STAGE {label} {event} {time.monotonic():.6f}\n")
        sys.stderr.flush()
    except Exception:
        pass


@contextmanager
def operation_stage(label: str) -> Iterator[None]:
    _mark(label, "begin")
    try:
        yield
    except BaseException:
        _mark(label, "failed")
        raise
    else:
        _mark(label, "end")
