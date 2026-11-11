"""Deduplicate exact shared cold-group proofs inside one live prepare call.

This is not a persisted or cross-call admission cache. Every source still
checks the entire actual archive and manifest hash. First use also verifies
all regular archive members and the original all-row initialization validator.
All per-source identities, references, controls and active guards remain live.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import hashlib
import json
from .gitlab_grouped_evidence_archive import VERSION, validate_reference

_SCOPE = ContextVar('gitlab_initialization_validation_scope', default=None)
# Exactly the complete fields read by _require_group_initialization. No
# caller's mutable object identity, actor task ID or certificate alone is a key.
FIELDS = (
    'native_before_initialization', 'protected_before', 'protected_after',
    'native_initialization_effects', 'native_initialization_record',
    'columns_before', 'columns_after', 'native_issue_cache_certification',
    'issue_cache_evidence',
)
MAX_SHARED_GROUPS = 64


@contextmanager
def validation_scope():
    token = _SCOPE.set({})
    try:
        yield
    finally:
        _SCOPE.reset(token)


def validate(cycle, validator):
    cache = _SCOPE.get()
    evidence = cycle.get('issue_cache_evidence') if isinstance(cycle, dict) else None
    if (cache is None or not isinstance(evidence, dict)
            or evidence.get('version') != VERSION):
        return validator(cycle)
    # Missing or altered initialization fields cannot reuse another source.
    content = hashlib.sha256(json.dumps({k: cycle[k] for k in FIELDS},
        sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).digest()
    # Distinct validation implementations never share authority even when the
    # input document is identical. The callable is retained for this scope.
    key = (validator, content)
    if key in cache:
        validate_reference(evidence)
        return deepcopy(cache[key])
    value = validator(cycle)
    if len(cache) < MAX_SHARED_GROUPS:
        cache[key] = deepcopy(value)
    return value
