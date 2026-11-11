"""One-use same-boundary CPU capture handoff; never a cross-action cache.

The producer has already taken a complete native snapshot immediately after its
actual full-state reset. Reuse that exact capture as the next prepare, or as the
group's final seal. Every terminal still gets its own independent full scan.
Normal actor construction does not expose this CPU-only ticket.
"""
from copy import deepcopy
import hashlib, json
from pathlib import Path
from .source_revision_binding import binding, fingerprint


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode()).hexdigest()


def action_boundary(site):
    """Call before every explicit public CPU action, including navigation."""
    epoch = getattr(site, '_native_cpu_action_epoch', 0)
    if type(epoch) is not int or epoch < 0:
        raise ValueError('Invalid CPU action boundary')
    site._native_cpu_action_epoch = epoch + 1


def identity(site):
    generation = getattr(site, 'generation', None)
    epoch = getattr(site, '_native_cpu_action_epoch', 0)
    if (getattr(site, 'domain', None) != 'reddit' or getattr(site, 'reuse_state', None) is not True
            or type(generation) is not int or generation < 1 or type(epoch) is not int or epoch < 0):
        raise ValueError('Actual full-reset reusable native instance required for handoff')
    return {'state_identity': hashlib.sha256(str(Path(site.state).absolute()).encode()).hexdigest(),
            'generation': generation, 'action_epoch': epoch,
            'selected_fingerprint': deepcopy(site.fingerprint())}


class FreshCapture:
    """An in-process, single-use reference to a retained full native capture."""
    def __init__(self, site, case, username, capture, raw_file):
        from .runtime_watchdog import require_watchdog
        from .reddit_parented_reply import validate_snapshot
        require_watchdog(); validate_snapshot(capture)
        self.site = site; self.boundary = identity(site)
        self.source = binding(case); self.fingerprint = fingerprint(case)
        self.username = username; self.capture = deepcopy(capture)
        self.raw_file = Path(raw_file); self.raw_bytes = self.raw_file.read_bytes()
        if json.loads(self.raw_bytes) != capture:
            raise ValueError('Same-boundary handoff must reference actual complete saved capture')
        self.capture_digest = digest(capture); self.used = False

    def consume(self, site, case, username):
        from .runtime_watchdog import require_watchdog
        require_watchdog()
        if self.used:
            raise ValueError('Fresh native capture handoff was already consumed')
        self.used = True  # even a rejected ticket cannot be recycled
        if (site is not self.site or identity(site) != self.boundary
                or binding(case) != self.source or fingerprint(case) != self.fingerprint
                or username != self.username or digest(self.capture) != self.capture_digest
                or self.raw_file.read_bytes() != self.raw_bytes):
            raise ValueError('Native capture handoff changed source, action/reset boundary or raw bytes')
        receipt = {'version': 'same-boundary-full13-cpu-handoff-v1',
                   'source_binding': deepcopy(self.source), 'fingerprint': self.fingerprint,
                   'boundary': deepcopy(self.boundary), 'raw_file': str(self.raw_file),
                   'raw_pin': {'bytes': len(self.raw_bytes), 'sha256': hashlib.sha256(self.raw_bytes).hexdigest()},
                   'capture_sha256': self.capture_digest, 'single_use': True,
                   'full_native_capture_retained': True, 'cross_action_reuse': False,
                   'actor_attempts': 0, 'api_calls': 0}
        return deepcopy(self.capture), receipt
