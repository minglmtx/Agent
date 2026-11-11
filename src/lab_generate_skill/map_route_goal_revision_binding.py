"""One explicit native coordinate-text training revision; no actor reference.

The original coordinate task and its source result remain unchanged. A complete
independent capability pins the declared resolver output, while actual full
native request/body receipts and existing cold lifecycle controls still gate
execution. This module performs no browser action, HTTP request or admission.
"""
from copy import deepcopy
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .map_route import capability_signature, LABELS
from .map_route_normal_capture import complete_route, exact_pair, fingerprint, native_request, point
from .source_revision_binding import binding, require_source_binding

VERSION = 'native-coordinate-search-derived-v1'
MODES = {'car': 'driving', 'bike': 'cycling', 'foot': 'walking'}
TASK_SUFFIX = '--native-resolved-training-v1'


def _read(reference):
    if (not isinstance(reference, dict) or set(reference) != {'file', 'sha256'}
            or not isinstance(reference['file'], str)
            or not re.fullmatch(r'[0-9a-f]{64}', str(reference['sha256']))):
        raise ValueError('Immutable independent capability file/hash required')
    path = Path(reference['file'])
    if 'actor' in path.parts or 'actor' in path.resolve().parts:
        raise ValueError('An actor artifact cannot supply a private native reference')
    try:
        data = path.read_bytes()
        value = json.loads(data)
    except (OSError, ValueError) as error:
        raise ValueError('Independent native capability artifact is unavailable') from error
    if hashlib.sha256(data).hexdigest() != reference['sha256']:
        raise ValueError('Independent native capability bytes changed')
    if not isinstance(value, dict):
        raise ValueError('Complete independent capability object required')
    return path, value


def mapping(contract):
    revision = contract.get('goal_revision')
    if not isinstance(revision, dict) or revision.get('version') != VERSION:
        raise ValueError('Known versioned native resolver goal revision required')
    value = revision.get('native_mapping')
    if not isinstance(value, dict) or set(value) != {'original_contract', 'capability_summary', 'capability_cycles', 'query_texts', 'profile'}:
        raise ValueError('Complete frozen-source and independent resolver mapping required')
    original = value['original_contract']
    if (not isinstance(original, dict) or original.get('domain') != 'map'
            or original.get('task_id') != contract['source_task_id']
            or original.get('source_task_id') != contract['source_task_id']
            or original.get('heldout_quarantine') is not False
            or original.get('task_text_changed') is not False
            or original.get('goal') != contract.get('original_goal')
            or original.get('start_path') != contract['start_path']
            or original.get('source_trace_ids') != contract['source_trace_ids']
            or original.get('recorded_start_paths') != contract['recorded_start_paths']
            or fingerprint(original) != contract['original_binding_sha256']):
        raise ValueError('Entire unchanged original exact-coordinate source required')
    original_route = original.get('completion', {}).get('map_route', {})
    original_pair = original_route.get('pair')
    profile = value['profile']
    if (profile not in MODES or contract.get('allowed_modes') != [profile]
            or {row.get('profile') for row in original_route.get('alternatives', [])} != {profile}):
        raise ValueError('Coordinate mapping must preserve the original single transport mode')
    texts = value['query_texts']
    if (not isinstance(texts, list) or len(texts) != 2
            or any(not isinstance(text, str) or len(text.split(',')) != 2 for text in texts)
            or not exact_pair([text.split(',') for text in texts], original_pair)
            or any(text not in original['goal'] for text in texts)
            or original['goal'].index(texts[0]) >= original['goal'].index(texts[1])):
        raise ValueError('Native search texts must retain both original numeric endpoints in order')
    summary_path, summary = _read(value['capability_summary'])
    if (summary_path.name != 'result.json'
            or any(summary.get(key) != expected for key, expected in {
                'status': 'captured', 'deterministic': True, 'independent_cycles': 2,
                'actor_attempts': 0, 'task_admissions': 0, 'api_calls': 0}.items())
            or type(summary.get('route_cases')) is not int or not 1 <= summary['route_cases'] <= 16):
        raise ValueError('Independent two-cold native capability receipt required')
    references = value['capability_cycles']
    if not isinstance(references, list) or len(references) != 2:
        raise ValueError('Both complete independent native capability cycles required')
    cycles = []
    selected = []
    for index, reference in enumerate(references):
        path, cycle = _read(reference)
        records = cycle.get('records')
        if (path != summary_path.parent / ('cycle-' + str(index)) / 'result.json'
                or cycle.get('status') != 'captured' or not isinstance(records, list) or len(records) != summary['route_cases']):
            raise ValueError('Complete ordered capability cycle files required')
        cycles.append([capability_signature(record) for record in records])
        matches = [record for record in records if record.get('origin') == texts[0]
            and record.get('destination') == texts[1] and record.get('profile') == profile]
        if len(matches) != 1:
            raise ValueError('One independently captured coordinate-text route in the original mode required')
        selected.append(matches[0])
    if cycles[0] != cycles[1]:
        raise ValueError('Complete native capability semantics differ across cold factories')
    native = selected[0].get('native', {})
    backend = selected[0].get('backend', {})
    legs = backend.get('legs', []) if isinstance(backend, dict) else []
    if (selected[0].get('error') is not None or not isinstance(native, dict)
            or native.get('engine') != LABELS[profile] or native.get('route_visible') is not True
            or native.get('loading') is not False or not native.get('rows')
            or len(legs) != 1 or not legs[0].get('steps')
            or {step.get('mode') for step in legs[0]['steps']} != {MODES[profile]}):
        raise ValueError('Native rendered engine and complete turn mode must preserve original transport')
    geocodes = selected[0].get('geocodes')
    if geocodes != selected[1].get('geocodes') or not isinstance(geocodes, list) or len(geocodes) != 2:
        raise ValueError('Both complete independent native query responses required')
    records = []
    for text, response in zip(texts, geocodes):
        parsed = urlsplit(response.get('request', ''))
        query = parse_qs(parsed.query, keep_blank_values=True)
        full = response.get('results')
        if (parsed.path != '/search' or parsed.scheme or parsed.netloc or response.get('status') != 200
                or query.get('q') != [text] or query.get('format') != ['json']
                or len(query.get('viewbox', [])) != 1 or not query['viewbox'][0]
                or not isinstance(full, list) or len(full) != 1):
            raise ValueError('Exact native text/viewbox query and unique complete response required')
        record = full[0]
        if (not isinstance(record, dict) or record.get('osm_type') not in ('node', 'way', 'relation')
                or type(record.get('osm_id')) is not int or record['osm_id'] <= 0
                or not isinstance(record.get('display_name'), str) or not record['display_name']):
            raise ValueError('Native resolver output object identity is incomplete')
        point([record.get('lat'), record.get('lon')])
        records.append(record)
    resolved = [[record['lat'], record['lon']] for record in records]
    if (not exact_pair(selected[0]['pair'], resolved)
            or not exact_pair(contract['endpoint_request'].get('pair'), resolved)
            or exact_pair(original_pair, resolved)):
        raise ValueError('A changed resolver endpoint must be declared exactly, not tolerated as original')
    return {'profile': profile, 'query_texts': deepcopy(texts), 'resolved_records': deepcopy(records),
            'resolved_pair': resolved, 'historical_native_route': deepcopy(selected[0]),
            'original_exact_pair': deepcopy(original_pair)}


def public_goal(value):
    endpoints = []
    for record in value['resolved_records']:
        endpoints.append(record['display_name'] + ' (' + record['osm_type'] + ' '
            + str(record['osm_id']) + '; ' + record['lat'] + ', ' + record['lon'] + ')')
    return ('Retrieve and display ' + MODES[value['profile']] + ' directions from ' + endpoints[0] + ' to ' + endpoints[1]
        + '. These are the local native text resolver outputs for "' + value['query_texts'][0]
        + '" and "' + value['query_texts'][1]
        + '". This explicit training derivative uses those resolved object identities and coordinates;'
        + ' it does not assert equivalence to the original exact numeric-coordinate route.')


def rendered_spec(value):
    """Full independent native display, with explicitly resolved endpoint labels."""
    # Existing native display rules use the capability's numeric UI pair;
    # exact Decimal request/resolver points remain separately bound above.
    return {'pair': deepcopy(value['historical_native_route']['pair']),
        'endpoint_labels': [[record['display_name']] for record in value['resolved_records']],
        'alternatives': [{'profile': value['profile'],
            'backend': deepcopy(value['historical_native_route']['backend']),
            'native': deepcopy(value['historical_native_route']['native'])}]}


def validate(contract):
    if contract.get('goal_revision',{}).get('version')=='native-named-destination-field-derived-v1':
        from .map_destination_field_goal_revision import validate as validate_field_derivative
        return validate_field_derivative(contract)
    binding(contract)
    if (contract.get('task_id') != contract['source_task_id'] + TASK_SUFFIX
            or contract.get('is_explicit_derivative') is not True
            or contract.get('original_evaluation_equivalence') is not False
            or contract.get('task_text_changed') is not True
            or contract.get('training_initialization') or contract.get('start_revision')
            or contract.get('initialization_revision') is not None
            or contract.get('task_text_revision') is not None
            or not isinstance(contract.get('allowed_modes'), list) or len(contract['allowed_modes']) != 1
            or contract['allowed_modes'][0] not in MODES
            or contract.get('completion_kind') != 'displayed_route'
            or contract.get('endpoint_request', {}).get('kind') != 'exact_points'
            or set(contract['endpoint_request']) != {'kind', 'pair'}):
        raise ValueError('Only an explicit unchanged-start native coordinate-text resolver derivative is supported')
    value = mapping(contract)
    if contract['goal'] != public_goal(value):
        raise ValueError('Public derivative must state its actual resolved identities/coordinates and non-equivalence')
    return value


def require_original_binding(contract, original, inventory):
    validate(contract)
    return require_source_binding(contract, original, inventory, domain='map')


def require_reference(contract, reference):
    """Complete independent read receipt; actual rollout uses the same capture.

    Every OSRM server exposes /route/v1/driving. The leased native origin role
    determines car/bike/foot; the shared URL path never establishes car mode.
    """
    value = validate(contract)
    receipt = reference.get('native_reference_receipt')
    origins = reference.get('native_service_origins')
    if (reference.get('native_goal_revision_version') != VERSION
            or reference.get('independent_native_read') is not True
            or not isinstance(receipt, dict) or not isinstance(origins, dict)
            or set(origins) != {'car', 'bike', 'foot'} or len(set(origins.values())) != 3
            or reference.get('native_reference_receipt_sha256') != fingerprint(receipt)
            or receipt.get('status') != 'complete_native_response' or receipt.get('http_status') != 200
            or receipt.get('native_only') is not True or receipt.get('external_fallback') is not False):
        raise ValueError('Complete independent native reference request/receipt required')
    from .map_native_route_reference_inventory import require_native_origin
    for origin in origins.values():
        require_native_origin(origin)
    request = native_request(receipt.get('requested_url', ''), origins)
    if (request is None or request['profile'] != value['profile']
            or not exact_pair(request['pair'], value['resolved_pair'])
            or request['request_path'] != value['historical_native_route']['native_backend_request_path']
            or reference.get('profile') != value['profile']
            or not exact_pair(reference.get('pair'), request['pair'])
            or reference.get('scope', {}).get('endpoint_request') != contract['endpoint_request']
            or reference.get('scope', {}).get('rendered_route_spec') != rendered_spec(value)):
        raise ValueError('Exact resolved native request and original leased transport role required')
    body_file = reference.get('native_raw_body_file')
    if (not isinstance(body_file, str) or 'actor' in Path(body_file).parts
            or 'actor' in Path(body_file).resolve().parts):
        raise ValueError('Independent raw native response artifact required')
    try:
        data = Path(body_file).read_bytes()
        body = json.loads(data)
    except (OSError, ValueError) as error:
        raise ValueError('Independent complete native body artifact is unavailable') from error
    if (len(data) != receipt.get('raw_body_bytes')
            or hashlib.sha256(data).hexdigest() != receipt.get('raw_body_sha256')
            or body != receipt.get('value') or body != reference.get('native_body')
            or reference.get('native_body_sha256') != fingerprint(body)
            or complete_route(body) != value['historical_native_route']['backend']):
        raise ValueError('Complete native body/waypoints and independent historical route disagree')
    return request


def reference_semantics(reference):
    """Remove leased addresses/artifact locations, preserving actual semantics.

    Complete receipts remain in each archived private snapshot. Exact request
    points/mode/options, HTTP/body bytes hash and count, every native body field,
    endpoint identities, rendered rows and source scope remain in this digest.
    """
    if reference.get('native_goal_revision_version') != VERSION:
        raise ValueError('Known native goal reference transport version required')
    receipt = reference.get('native_reference_receipt')
    if (not isinstance(receipt, dict)
            or reference.get('native_reference_receipt_sha256') != fingerprint(receipt)):
        raise ValueError('Exact native transport receipt required before semantic comparison')
    request = native_request(receipt.get('requested_url', ''), reference.get('native_service_origins', {}))
    if request is None:
        raise ValueError('Actual native routing request cannot disappear from its semantic digest')
    result = deepcopy(reference)
    for key in ('native_reference_receipt_sha256', 'native_reference_receipt',
                'native_service_origins', 'native_raw_body_file'):
        result.pop(key)
    # All receipt fields except leased URL and artifact basename remain bound.
    result['native_transport_semantics'] = {key: deepcopy(value) for key, value in receipt.items()
        if key not in ('requested_url', 'raw_body_file')}
    result['native_transport_semantics']['actual_request'] = request
    return result
