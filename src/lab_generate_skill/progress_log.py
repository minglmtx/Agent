"""Throttle operational progress only; callers still validate every input row."""
import time
from pathlib import Path
from .io_utils import append_jsonl


class ProgressLog:
    def __init__(self, path, *, interval=5.0, clock=time.monotonic):
        self.path = Path(path) if path is not None else None
        self.interval = interval
        self.clock = clock
        self.last = {}
        self.pending = {}

    def record(self, key, row):
        if self.path is None:
            return
        now = self.clock()
        self.pending[key] = dict(row)
        if key not in self.last or now-self.last[key] >= self.interval:
            self.flush(key)
            self.last[key] = now

    def flush(self, key=None):
        keys = list(self.pending) if key is None else [key]
        rows = [self.pending[k] for k in keys if k in self.pending]
        if rows:
            append_jsonl(self.path, rows, durable=False)
            for k in keys:
                self.pending.pop(k, None)
