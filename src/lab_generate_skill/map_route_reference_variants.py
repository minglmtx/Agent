"""Private references for all independently identified endpoints of a named place.

No alternative is inferred from an actor action, fuzzy coordinate match, or
provider rank. Existing single-reference proofs retain their original format.
"""
from copy import deepcopy
import re

from .map_route_normal_capture import exact_pair, fingerprint, point


def pair_key(pair):
    if not isinstance(pair, list) or len(pair) != 2:
        raise ValueError('Two complete route endpoints required')
    return tuple(tuple(point(endpoint)) for endpoint in pair)


def entries(proof, profile=None):
    primary = proof.get('references', {})
    alternatives = proof.get('reference_alternatives', {})
    for mode, reference in primary.items():
        if profile is None or mode == profile:
            for value in alternatives.get(mode, [reference]):
                yield mode, value


def matching_reference(proof, profile, pair):
    matches = [ref for _, ref in entries(proof, profile) if exact_pair(ref.get('pair'), pair)]
    if len(matches) > 1:
        raise ValueError('Duplicate private route reference for one mode and endpoint pair')
    return matches[0] if matches else None


def declared_pairs(contract, evidence):
    """Recompute full endpoint choices from the original query and native records."""
    from .map_native_identity_declarations import declare_query
    from .native_route_metadata import diagnostic_pairs

    kind = contract['endpoint_request']['kind']
    if kind not in ('named_places', 'reverse_named_initial_route', 'replace_one_endpoint'):
        raise ValueError('Named alternatives cannot broaden a fixed-coordinate or free-choice task')
    request = contract['endpoint_request']
    queries = ([request['query']] if kind == 'replace_one_endpoint' else
               request['queries'] if kind == 'named_places' else request['initial_queries'])
    if not isinstance(evidence, dict) or set(evidence) != set(queries):
        raise ValueError('Complete evidence for exactly the original endpoint queries required')
    reviews = {}
    for query in queries:
        native = evidence[query]
        if (not isinstance(native, dict) or native.get('query') != query
                or not re.fullmatch(r'[0-9a-f]{64}', str(native.get('native_receipt_sha256', '')))):
            raise ValueError('Original query and full native receipt must be bound')
        reviews[query] = declare_query(query, native)
    values = diagnostic_pairs(contract, {'geocodes': evidence}, reviews)
    pairs = [deepcopy(value['pair']) for value in values]
    if kind == 'reverse_named_initial_route':
        pairs = [list(reversed(pair)) for pair in pairs]
    keys = [pair_key(pair) for pair in pairs]
    if not keys or len(keys) != len(set(keys)):
        raise ValueError('Distinct complete native endpoint variants required')
    return pairs


def validate_variants(contract, proof):
    if 'reference_alternatives' not in proof:
        if 'named_endpoint_evidence' in proof:
            raise ValueError('Named variant evidence requires the complete alternative reference set')
        return
    alternatives = proof['reference_alternatives']
    primary = proof.get('references', {})
    if (not isinstance(alternatives, dict) or not alternatives
            or set(alternatives) != set(primary) or set(primary) != set(contract['allowed_modes'])):
        raise ValueError('Every allowed mode must retain all named endpoint alternatives')
    pairs = declared_pairs(contract, proof.get('named_endpoint_evidence'))
    expected = {pair_key(pair) for pair in pairs}
    for profile, refs in alternatives.items():
        if not isinstance(refs, list) or not refs or any(not isinstance(ref, dict) for ref in refs):
            raise ValueError('Complete named route reference list required')
        keys = [pair_key(ref.get('pair')) for ref in refs]
        if len(keys) != len(set(keys)) or set(keys) != expected:
            raise ValueError('Named reference pairs omit or invent a native endpoint variant')
        if sum(ref == primary[profile] for ref in refs) != 1:
            raise ValueError('Primary reference must be an unchanged member of the full set')
        if any(ref.get('scope', {}).get('endpoint_request') != contract['endpoint_request'] for ref in refs):
            raise ValueError('Each alternative must preserve the original endpoint request')


def variant_control_keys(proof):
    return sorted(fingerprint({'profile': profile, 'pair': [[str(v) for v in point(p)] for p in ref['pair']],
                               'native_body_sha256': ref['native_body_sha256']})
                  for profile, ref in entries(proof))


def require_variant_controls(proof, cycle):
    if 'reference_alternatives' not in proof:
        return
    rows = cycle.get('named_endpoint_variant_controls')
    if (not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows)
            or sorted(row.get('reference_key', '') for row in rows) != variant_control_keys(proof)
            or any(row.get('correct_terminal_passed') is not True
                   or row.get('wrong_endpoint_rejected') is not True for row in rows)):
        raise ValueError('Every named route variant needs positive and wrong-endpoint controls in both cold runs')
