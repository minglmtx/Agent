"""Private candidate for coincident native named routing endpoints.

This does not choose an OSM ID, admit a task, or claim polygon/object equality.
Callers must independently bind the complete native response and this semantic
review to the actual response receipt and the unchanged source task. Every
matching identity remains an alternative; the candidate proves only the exact
coordinate endpoint is shared. Failure to declare remains an unknown reference.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

VERSION = 'native-coincident-routing-alias-candidate-v1'
BASE_CHECKS = frozenset(('full_native_object_identity', 'native_coordinate_valid',
                        'requested_semantic_name', 'country', 'requested_region',
                        'requested_feature_kind'))
ANCHOR_KEYS = ('wikipedia', 'nist:fips_code')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError('Native exact numeric value required')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Native exact numeric value malformed') from exc
    if not result.is_finite():
        raise ValueError('Finite native coordinate required')
    return result


def native_geography(record):
    point = number(record['lat']), number(record['lon'])
    raw_bounds = record['boundingbox']
    if not isinstance(raw_bounds, list) or len(raw_bounds) != 4:
        raise ValueError('Complete native extent required')
    south, north, west, east = map(number, raw_bounds)
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180
            and south <= point[0] <= north and west <= point[1] <= east):
        raise ValueError('Native endpoint is outside its declared geographic extent')
    return point, (south, north, west, east)


def declare_coincident_routing_alias(review):
    """Require exact native endpoint/extent and two native same-domain anchors.

    Bounding boxes do not prove polygons identical. The additional anchors
    support the native alias interpretation; no provider rank, name precedence,
    coordinate tolerance or arbitrary first member is used.
    """
    if review.get('status') != 'ambiguous_native_identity':
        raise ValueError('Existing multi-identity semantic review required')
    query = review['query']
    native = review['full_native_query_evidence']
    records = native.get('full_records')
    if (native.get('query') != query
            or native.get('status') != 'full_identity_candidates_require_declaration'
            or not re.fullmatch('[0-9a-f]{64}', native.get('native_receipt_sha256', ''))
            or not isinstance(records, list) or not records
            or review.get('first_result_rank_used') is not False
            or review.get('actor_or_later_published_step_used') is not False):
        raise ValueError('Exact original complete native semantic evidence required')
    inspected = review.get('all_native_record_checks')
    if not isinstance(inspected, list) or len(inspected) != len(records):
        raise ValueError('Every full native record and rejection must remain present')
    matches = []
    for record, row in zip(records, inspected):
        if row.get('full_geocode_record') != record or row.get('full_geocode_sha256') != fingerprint(record):
            raise ValueError('Full native record bytes no longer match semantic review')
        checks = row.get('checks')
        if not isinstance(checks, dict) or not BASE_CHECKS <= checks.keys() or any(type(v) is not bool for v in checks.values()):
            raise ValueError('Complete native identity/kind/region/name checks required')
        if all(checks.values()):
            identity = record.get('osm_type'), record.get('osm_id')
            if identity[0] not in ('node', 'way', 'relation') or type(identity[1]) is not int or identity[1] <= 0:
                raise ValueError('Native object identity missing')
            matches.append((identity, record))
    if len(matches) < 2 or review.get('matching_native_record_count') != len(matches):
        raise ValueError('At least two actual matching native alternatives required')
    if len({identity for identity, _ in matches}) != len(matches):
        raise ValueError('Duplicate copies are unresolved provider output, not aliases')
    geography = [native_geography(record) for _, record in matches]
    if any(item != geography[0] for item in geography[1:]):
        raise ValueError('Different native endpoints or extents remain unresolved')
    shared = {}
    for key in ANCHOR_KEYS:
        values = [record.get('extratags', {}).get(key) for _, record in matches]
        if any(not isinstance(value, str) or not value.strip() for value in values) or len(set(values)) != 1:
            raise ValueError('Native same-domain alias anchors are absent or conflicting')
        shared[key] = values[0]
    point, bounds = geography[0]
    group = {'version': VERSION, 'requested_query': query,
             'native_receipt_sha256': native['native_receipt_sha256'],
             'policy_sha256': review['policy_sha256'],
             'native_point': [str(value.normalize()) for value in point],
             'native_bounds': [str(value.normalize()) for value in bounds],
             'matching_full_native_records': [deepcopy(record) for _, record in matches],
             'shared_native_anchors': shared,
             'full_native_query_evidence': deepcopy(native),
             'all_native_record_checks': deepcopy(inspected),
             'routing_endpoint_only': True, 'polygon_equivalence_claimed': False,
             'object_identity_equivalence_claimed': False, 'selected_osm_id': None,
             'normal_admission': False, 'actor_attempts': 0, 'api_calls': 0}
    group['group_sha256'] = fingerprint(group)
    return group
