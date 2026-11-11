"""Bounded shared-backend preparation for source-bound route candidates.

This captures prerequisites only. It neither scores actors nor grants admission:
native page rendering, initialization and reset still need the normal gate.
"""
from copy import deepcopy
from urllib.parse import parse_qs, urlsplit, urlencode
from pathlib import Path
import time

from .source_revision_binding import binding
from .map_route_normal_capture import point, fingerprint, complete_route
from .map_native_route_reference_inventory import full_http, require_native_origin
from .map_native_identity_declarations import declare_query
from .native_route_metadata import diagnostic_pairs, exact_native_endpoint
from .map_named_endpoint_alternatives import declare_named_endpoint_alternatives
from .io_utils import atomic_write_json


def backend_spec(candidate):
    source = binding(candidate)
    c = candidate['candidate_completion']
    if candidate.get('split') != 'train' or c.get('family') != 'displayed_route':
        raise ValueError('Training route candidate required')
    mode = c.get('profile')
    if mode not in ('car', 'bike', 'foot'):
        raise ValueError('Explicit transport profile required')
    metric = c.get('optimization_metric')
    if metric not in (None, 'distance', 'duration'):
        raise ValueError('Unknown route comparison metric')
    request = deepcopy(c['endpoint_request'])
    if request.get('kind') == 'named_places':
        queries = request.get('queries')
        if not isinstance(queries, list) or len(queries) != 2 or any(not isinstance(q, str) or not q.strip() for q in queries):
            raise ValueError('Two explicit named endpoints required')
    elif request.get('kind') == 'replace_one_endpoint':
        p = urlsplit(candidate['start_path']); q = parse_qs(p.query)
        if (p.path != '/directions' or q.get('engine') != ['fossgis_osrm_' + mode]
                or len(q.get('route', [])) != 1 or request.get('replace') != 'destination'
                or not isinstance(request.get('query'), str) or not request['query'].strip()):
            raise ValueError('Declared initial route and replacement must agree')
        pair = q['route'][0].split(';')
        if len(pair) != 2 or point(pair[0].split(',')) != point(request.get('preserved_origin')):
            raise ValueError('Preserved origin differs from declared initial route')
        if point(pair[0].split(',')) == point(pair[1].split(',')):
            raise ValueError('Initial route has identical endpoints')
        request['changed'] = request.pop('replace')
        request['retained_pair'] = q['route'][0]
        request['unchanged_peer_backend_point_must_remain_exact'] = True
        request['source'] = ('explicit_published_derived_start' if candidate.get('start_revision')
                             else 'explicit_original_goal_and_original_first_route_url')
    else:
        raise ValueError('Unsupported route endpoint definition')
    return {'source_task_id': candidate['source_task_id'], 'goal': candidate['goal'],
            'start_path': candidate['start_path'], 'endpoint_request': request,
            'initial_route_required': candidate['start_path'] if request['kind']=='replace_one_endpoint' else None,
            'allowed_modes': [mode], 'initialization_revision': candidate.get('start_revision'),
            'candidate_binding_sha256': fingerprint(source), 'comparison_metric': metric,
            'task_admitted': False}


def candidate_pairs(spec, inventory, reviews):
    """Support an explicitly published derived start without calling it original."""
    request = spec['endpoint_request']
    if request.get('source') != 'explicit_published_derived_start':
        return diagnostic_pairs(spec, inventory, reviews)
    revision = spec.get('initialization_revision')
    if (not isinstance(revision, dict) or revision.get('equivalent_to_original') is not False
            or revision.get('derived_start') != spec['start_path']
            or not revision.get('original_start') or not revision.get('reason')
            or request.get('kind') != 'replace_one_endpoint'
            or request.get('changed') != 'destination'
            or request.get('unchanged_peer_backend_point_must_remain_exact') is not True):
        raise ValueError('Complete explicit derived initial route required')
    parsed = urlsplit(spec['start_path']); query = parse_qs(parsed.query)
    if (parsed.scheme or parsed.netloc or parsed.path != '/directions'
            or query.get('route') != [request['retained_pair']]
            or query.get('engine') != ['fossgis_osrm_' + spec['allowed_modes'][0]]):
        raise ValueError('Derived route state differs from published initialization')
    initial = [point(p.split(',')) for p in request['retained_pair'].split(';')]
    if len(initial) != 2 or point(request['preserved_origin']) != initial[0]:
        raise ValueError('Derived route must retain the declared origin')
    name = request['query']; native = inventory['geocodes'][name]; review = reviews[name]
    try:
        endpoints = [exact_native_endpoint(name, native, review)]
    except ValueError:
        if review.get('full_native_query_evidence') != native:
            raise ValueError('Derived endpoint review does not bind native response')
        endpoints = declare_named_endpoint_alternatives(review)['alternatives']
    results = []
    for endpoint in endpoints:
        destination = point(endpoint['point'])
        if destination in initial:
            raise ValueError('Replacement must change the destination without a degenerate route')
        results.append({'pair': [[str(v) for v in initial[0]], list(endpoint['point'])],
                        'initial_pair': [[str(v) for v in p] for p in initial],
                        'scope': 'explicit_published_derived_initial_route',
                        'initialization_revision': deepcopy(revision),
                        'normal_admission': False, 'provider_rank_used': False})
    return results


def collect(site, candidates, directory, *, deadline, request_limit=32):
    """Read each distinct name once and retain complete native response bytes."""
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=False)
    specs = [backend_spec(c) for c in candidates]
    if len({s['source_task_id'] for s in specs}) != len(specs):
        raise ValueError('Duplicate candidate task')
    search = require_native_origin(site.search_url)
    routers = {k: require_native_origin(v) for k, v in site.route_urls.items()}
    if set(routers) != {'car', 'bike', 'foot'} or len(set(routers.values())) != 3:
        raise ValueError('Distinct mode-specific native services required')
    queries = sorted({q for s in specs for q in
                      (s['endpoint_request'].get('queries') or [s['endpoint_request']['query']])})
    geocodes = {}; reviews = {}; count = 0
    def read(url, folder, name):
        nonlocal count
        if count >= request_limit or time.monotonic() >= deadline:
            raise TimeoutError('Shared candidate batch request/time budget reached')
        count += 1
        return full_http(url, directory / folder, name, deadline)
    result = {'scope': 'backend_capability_only', 'tasks': [], 'geocodes': geocodes,
              'native_controls_passed': False, 'actor_attempts': 0, 'training_admitted': False,
              'api_calls': 0, 'request_limit': request_limit, 'completed': False}
    try:
        for i, query in enumerate(queries):
            receipt = read(search + '/search?' + urlencode({'q': query, 'format': 'jsonv2',
                           'addressdetails': 1, 'namedetails': 1, 'extratags': 1, 'limit': 50}), 'geocodes', str(i))
            records = receipt.get('value')
            ok = receipt.get('status') == 'complete_native_response' and isinstance(records, list)
            # An at-limit result might omit another valid object. Do not pick rank 1.
            status = ('full_identity_candidates_require_declaration' if ok and 0 < len(records) < 50
                      else 'query_at_limit_requires_followup' if ok and len(records) >= 50
                      else 'native_geographic_coverage_unavailable')
            native = {'query': query, 'native_receipt_sha256': fingerprint(receipt),
                      'full_records': records if ok else None, 'status': status}
            geocodes[query] = native; reviews[query] = declare_query(query, native)
        cache = {}
        for spec in specs:
            row = {'source_task_id': spec['source_task_id'], 'candidate_binding_sha256': spec['candidate_binding_sha256'],
                   'status': 'independent_identity_review_required', 'native_admitted': False, 'references': []}
            try:
                variants = candidate_pairs(spec, {'geocodes': geocodes}, reviews)
                mode = spec['allowed_modes'][0]
                for variant in variants:
                    pair = variant['pair']; key = fingerprint({'profile': mode, 'pair': pair})
                    if key not in cache:
                        coords = ';'.join(str(point(p)[1]) + ',' + str(point(p)[0]) for p in pair)
                        # Match actual native browser request: no hidden alternative-route protocol.
                        receipt = read(routers[mode] + '/route/v1/driving/' + coords +
                                       '?overview=false&steps=true&geometries=polyline', 'routes', key)
                        if receipt.get('status') != 'complete_native_response':
                            raise ValueError('Native route response unavailable')
                        route = complete_route(receipt['value'])
                        cache[key] = {'profile': mode, 'pair': pair, 'receipt_file': 'routes/' + key + '.receipt.json',
                                      'receipt_sha256': fingerprint(receipt), 'distance': route['distance'],
                                      'duration': route['duration'], 'routes_returned': len(receipt['value']['routes'])}
                    row['references'].append(deepcopy(cache[key]))
                row['status'] = 'backend_candidates_captured_native_page_controls_pending'
                row['comparison_scope'] = 'Only routes returned by the actual native request; no global optimum claim'
            except (ValueError, KeyError, TypeError) as error:
                row['error'] = {'type': type(error).__name__, 'message': str(error)}
            result['tasks'].append(row)
            atomic_write_json(directory / 'result.json', result)
        result['completed'] = len(result['tasks']) == len(specs)
    finally:
        result['native_requests'] = count
        atomic_write_json(directory / 'result.json', result)
    return result
