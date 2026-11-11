"""Additional archived-route evidence; never replace the original row digest.

The current runtime can consume this explicitly versioned evidence. Historical
frozen callbacks and raw rows retain their original bytes and digests.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlsplit, parse_qs

from .map_route_normal_capture import fingerprint

VERSION = 'archived-native-route-reference-semantics-v2'


def reference_snapshot(proof):
    # A canonical runtime imports this helper before defining its functions.
    from .map_route_normal_runtime import reference_snapshot as original_snapshot
    return original_snapshot(proof)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_relative(name):
    value = PurePosixPath(name)
    if value.is_absolute() or '..' in value.parts or value.as_posix() != name:
        raise ValueError('Exact relative original evidence locator required')
    return value


def derive(original_path, expected_file_sha256, expected_legacy_semantics):
    """Read the complete original JSON, receipts and bodies at original paths."""
    from .map_route_normal_runtime import reference_semantics
    path = Path(original_path)
    if not path.is_absolute():
        raise ValueError('Original absolute private-reference locator required')
    raw = path.read_bytes()
    if sha(raw) != expected_file_sha256:
        raise ValueError('Original private-reference bytes changed')
    proof = json.loads(raw)
    legacy = fingerprint(legacy_reference_semantics(proof))
    if legacy != expected_legacy_semantics:
        raise ValueError('Stored original semantic digest differs from frozen algorithm')
    inventory = path.parent / 'full-native-inventory'
    bindings = []
    for query, evidence in sorted(proof.get('named_endpoint_evidence', {}).items()):
        receipt_path = inventory / safe_relative(evidence['native_receipt'])
        receipt_raw = receipt_path.read_bytes()
        receipt = json.loads(receipt_raw)
        body_path = receipt_path.parent / safe_relative(receipt['raw_body_file'])
        body = body_path.read_bytes()
        requested = urlsplit(receipt['requested_url'])
        if (evidence.get('query') != query
                or fingerprint(receipt) != evidence.get('native_receipt_sha256')
                or receipt.get('status') != 'complete_native_response'
                or receipt.get('http_status') != 200
                or receipt.get('native_only') is not True
                or receipt.get('external_fallback') is not False
                or requested.hostname not in ('127.0.0.1', 'localhost')
                or requested.path != '/search'
                or parse_qs(requested.query).get('q') != [query]
                or len(body) != receipt.get('raw_body_bytes')
                or sha(body) != receipt.get('raw_body_sha256')
                or json.loads(body) != receipt.get('value')
                or receipt.get('value') != evidence.get('full_records')):
            raise ValueError('Complete original named query/receipt/body binding differs')
        bindings.append({'query': query, 'original_receipt_path': str(receipt_path),
                         'receipt_file_sha256': sha(receipt_raw),
                         'receipt_semantic_sha256': fingerprint(receipt),
                         'original_body_path': str(body_path),
                         'body_sha256': sha(body), 'body_bytes': len(body),
                         'full_records_sha256': fingerprint(receipt['value'])})
    if not bindings:
        raise ValueError('Complete named-route native evidence required')
    return {'version': VERSION, 'original_private_reference_path': str(path),
            'original_private_reference_file_sha256': sha(raw),
            'original_reference_set_sha256': fingerprint(reference_snapshot(proof)),
            'original_private_reference_semantics_sha256': legacy,
            'derived_reference_semantics_sha256': fingerprint(reference_semantics(proof)),
            'named_native_body_bindings': bindings,
            'original_records_modified': False}


def require_derived_evidence(cycle, native, proof):
    """Reject declared metadata unless it recomputes from supplied raw bytes."""
    if proof.get('route_reference_semantics_version') != VERSION:
        raise ValueError('Explicit versioned original-route consumption required')
    actual = cycle.get('actual_cycle') or {}
    relative = safe_relative(cycle['private_reference_artifact_relative_path'])
    source = cycle['source_task_id']
    if relative.parts[0] != source:
        raise ValueError('Private evidence escaped its exact source subtree')
    original = Path(actual['original_producer_output_directory']) / relative
    expected = derive(original, cycle['private_reference_artifact_file_sha256'],
                      cycle['private_reference_semantics_sha256'])
    if cycle.get('derived_route_reference_semantics') != expected:
        raise ValueError('Derived reference evidence differs from original full bytes')
    if (json.loads(original.read_bytes()) != native
            or expected['original_reference_set_sha256'] != cycle['private_reference_set_sha256']):
        raise ValueError('Actual private snapshot/reference set differs from original bytes')
    return expected['derived_reference_semantics_sha256']


# The exact frozen reference_semantics function is appended by revalidate.py,
# renamed to legacy_reference_semantics. Its source and SHA are recorded.

def legacy_reference_semantics(proof):
    """Only ephemeral HTTP receipt hashes differ across leased cold origins.

    Keep full actual receipt hashes in each independent snapshot; this separate
    signature retains exact backend body, endpoint/OSM identity, native visible
    reference, mode, source scope, field and optimization semantics. Never strip
    coordinates, task data, object IDs, rendered rows or source definitions.
    """
    value=reference_snapshot(proof)
    refs=list((value.get('references')or{}).values())
    if 'initial_native_reference' in value:refs.append(value['initial_native_reference'])
    refs.extend(ref for alternatives in (value.get('reference_alternatives')or{}).values() for ref in alternatives)
    for ref in refs:
        receipt=ref.get('native_reference_receipt_sha256')
        if not re.fullmatch(r'[0-9a-f]{64}',str(receipt)):
            raise ValueError('Actual independent native transport receipt SHA required')
        if ref.get('native_goal_revision_version') is not None:
            from .map_route_goal_revision_binding import reference_semantics as goal_reference_semantics
            semantic=goal_reference_semantics(ref)
            ref.clear();ref.update(semantic)
        else:
            del ref['native_reference_receipt_sha256']
    for evidence in (value.get('named_endpoint_evidence')or{}).values():
        receipt=evidence.get('native_receipt_sha256')
        if not re.fullmatch(r'[0-9a-f]{64}',str(receipt)):
            raise ValueError('Complete native endpoint receipt SHA required')
        del evidence['native_receipt_sha256']
    return value
