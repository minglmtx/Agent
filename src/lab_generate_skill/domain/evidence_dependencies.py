"""Enumerate typed references in validated contract data without I/O.

Only declared Contract fields and immutable tuples are traversed. Opaque JSON,
strings and lookalike dictionaries are not interpreted as evidence links. Keep
declaration order and duplicates; consumers choose their own read deduplication.
"""

from .evidence import EvidenceRef
from .validation import Contract


def evidence_references(value: object) -> tuple[EvidenceRef, ...]:
    if isinstance(value, EvidenceRef):
        return (value,)
    if isinstance(value, Contract):
        return tuple(
            reference
            for name in type(value).model_fields
            for reference in evidence_references(getattr(value, name))
        )
    if isinstance(value, tuple):
        return tuple(
            reference for item in value for reference in evidence_references(item)
        )
    return ()
