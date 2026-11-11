"""Persist failed private reference calls outside the resettable website state.

Only byte counts and hashes are attached to the exception for public summaries.
The bounded raw streams remain in the worker's private diagnostic archive.
"""
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

STREAM_LIMIT = 256 * 1024


def _stream(value):
    raw = value if isinstance(value, bytes) else (value or '').encode('utf-8', errors='replace')
    bounded = raw if len(raw) <= STREAM_LIMIT else raw[:STREAM_LIMIT // 2] + raw[-STREAM_LIMIT // 2:]
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
            'truncated': len(raw) > STREAM_LIMIT,
            'retained_prefix_and_suffix': len(raw) > STREAM_LIMIT,
            'base64': base64.b64encode(bounded).decode('ascii')}


def retain_private_failure(site, error, *, browser_stage=None):
    """Best effort diagnostics must never replace the original execution error."""
    logs = getattr(site, 'logs', None)
    if logs is None:
        return
    try:
        logs = Path(logs)
        # Do not create a new unbound output tree or follow an output symlink.
        if not logs.is_dir() or logs.is_symlink():
            raise ValueError('Existing native worker log directory required')
        value = {'version': 'private-native-failure-v1', 'time': time.time(),
                 'exception_type': type(error).__name__,
                 'returncode': getattr(error, 'returncode', None),
                 'timeout_seconds': getattr(error, 'timeout', None),
                 'stdout': _stream(getattr(error, 'stdout', None)),
                 'stderr': _stream(getattr(error, 'stderr', None))}
        if browser_stage is not None:
            if browser_stage not in ('subscription_feed_fetch', 'subscription_browser_capture'):
                raise ValueError('Known browser diagnostic stage required')
            value['browser_stage'] = browser_stage
            value['message'] = _stream(str(error))
        path = logs / 'private-native-failures.jsonl'
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'a', encoding='utf-8') as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            os.fchmod(stream.fileno(), 0o600)
            stream.write(json.dumps(value, separators=(',', ':'), allow_nan=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        # The control producer already whitelists these non-sensitive fields.
        error.record = {'stage': 'request_timeout' if isinstance(error, subprocess.TimeoutExpired)
                        else 'process_exited', 'returncode': value['returncode'],
                        'stderr_bytes': value['stderr']['bytes'],
                        'stderr_sha256': value['stderr']['sha256']}
        if browser_stage is not None:
            error.record.update(stage=browser_stage, message_bytes=value['message']['bytes'],
                                message_sha256=value['message']['sha256'])
    except Exception as diagnostic_error:
        # Preserve the primary error even when storage is full or unavailable.
        error.private_diagnostic_error_type = type(diagnostic_error).__name__
