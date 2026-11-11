"""Persist private native-reader diagnostics even when subprocesses fail.

This does not retry commands or change their exceptions. Request credentials
are excluded, and matching values in output are redacted before persistence.
"""
import hashlib
import json
from pathlib import Path
import re
import time

from .io_utils import atomic_write_json


def _secrets(value):
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if re.search(r'password|secret|token|credential|authorization', key, re.I):
                if isinstance(item, str) and item:
                    found.add(item)
            found.update(_secrets(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.update(_secrets(item))
    return found


def invoke_with_receipt(invoke, *, directory, script, request, metadata=None):
    """Invoke once and preserve return code/output for success, error or timeout."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'native-invocation.json'
    secrets = _secrets(request)
    tokens = set(secrets)
    for value in secrets:
        tokens.add(json.dumps(value, ensure_ascii=True)[1:-1])
        tokens.add(json.dumps(value, ensure_ascii=False)[1:-1])

    def output(value):
        raw = value if isinstance(value, bytes) else (value or '').encode()
        text = raw.decode('utf-8', errors='replace')
        for token in sorted(tokens, key=len, reverse=True):
            text = text.replace(token, '[REDACTED]')
        return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                'redacted_text': text}

    receipt = dict(metadata or {})
    receipt.update(status='started', script_sha256=hashlib.sha256(script.encode()).hexdigest())

    def save():
        atomic_write_json(path, receipt)
        path.chmod(0o600)

    save()
    start = time.monotonic()
    try:
        result = invoke()
    except BaseException as error:
        receipt.update(status='interrupted' if not isinstance(error, Exception) else 'error',
                       error_type=type(error).__name__,
                       returncode=getattr(error, 'returncode', None),
                       timeout_seconds=getattr(error, 'timeout', None),
                       stdout=output(getattr(error, 'stdout', None)),
                       stderr=output(getattr(error, 'stderr', None)))
        raise
    else:
        receipt.update(status='success' if result.returncode == 0 else 'error',
                       returncode=result.returncode,
                       stdout=output(result.stdout), stderr=output(result.stderr))
        return result
    finally:
        receipt['elapsed_seconds'] = time.monotonic() - start
        save()
