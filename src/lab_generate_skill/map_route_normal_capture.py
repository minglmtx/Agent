"""Private normal-route proof capture; no navigation, route injection or actor strategy.

Reference creation and task admissions are separate stages. This module records
the actually served native OSRM requests before their page is evaluated. Exact
request coordinates remain authoritative when the native UI rounds a URL or
when Nominatim resolves a coordinate string to a nearby, different OSM object.
"""
from decimal import Decimal, InvalidOperation
import base64
import binascii
import re
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        allow_nan=False).encode()).hexdigest()


def point(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError('A complete latitude/longitude is required')
    if any(isinstance(v, bool) for v in value):
        raise ValueError('Boolean is not a coordinate')
    try:
        pair = [Decimal(str(v)) for v in value]
    except (ValueError, InvalidOperation) as error:
        raise ValueError('Invalid native endpoint') from error
    if (any(not v.is_finite() for v in pair) or not -90 <= pair[0] <= 90
            or not -180 <= pair[1] <= 180):
        raise ValueError('Native endpoint is outside geographic bounds')
    return pair


def exact_pair(left, right):
    if not isinstance(left, list) or not isinstance(right, list) or len(left) != 2 or len(right) != 2:
        return False
    try:
        return all(point(a) == point(b) for a, b in zip(left, right))
    except ValueError:
        return False


def native_request(url, origins):
    """Only exact currently leased native OSRM origins, with full steps."""
    parsed = urlsplit(url)
    matched = [p for p, origin in origins.items()
        if (urlsplit(origin).scheme, urlsplit(origin).netloc) == (parsed.scheme, parsed.netloc)]
    if not matched:
        return None
    if len(matched) != 1 or matched[0] not in ('car', 'bike', 'foot'):
        raise ValueError('Native OSRM origin has an ambiguous transport role')
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError('Malformed actual native route request')
    prefix = '/route/v1/driving/'
    if not parsed.path.startswith(prefix):
        return None
    raw = parsed.path[len(prefix):].split(';')
    if len(raw) != 2:
        raise ValueError('Native route request must contain two endpoints')
    pair = []
    for value in raw:
        lonlat = value.split(',')
        if len(lonlat) != 2:
            raise ValueError('Malformed native request coordinate')
        latlon = point([lonlat[1], lonlat[0]])
        pair.append([str(v) for v in latlon])
    query = parse_qs(parsed.query, keep_blank_values=True)
    if query.get('steps') != ['true'] or query.get('overview') != ['false']:
        raise ValueError('Native normal route must capture the complete turn response')
    if set(query) - {'steps', 'overview', 'geometries', 'alternatives', 'hints'}:
        raise ValueError('Unreviewed native route request option')
    if 'hints' in query:
        # Native OSRM reuses waypoint hints on reverse/recalculate operations.
        # Hints are opaque endpoint-position caches, not different goals. Keep
        # the exact URL; downstream endpoint, full-body and display checks stay
        # unchanged. OSRM arrays contain one optional hint per input coordinate.
        values = query['hints']
        if len(values) != 1 or len(values[0].split(';')) != len(pair):
            raise ValueError('Native route hints must match the two endpoints')
        for hint in values[0].split(';'):
            if not hint:
                continue
            if re.fullmatch(r'[A-Za-z0-9_+/-]+={0,2}', hint) is None:
                raise ValueError('Malformed native waypoint hint')
            try:
                base64.b64decode(hint + '=' * (-len(hint) % 4), altchars=b'-_', validate=True)
            except (ValueError, binascii.Error) as error:
                raise ValueError('Malformed native waypoint hint') from error
    if query.get('geometries', ['polyline']) not in [['polyline'], ['polyline6'], ['geojson']]:
        raise ValueError('Unsupported native response geometry')
    if query.get('alternatives', ['false']) != ['false']:
        raise ValueError('Multiple native routes require an explicit alternative protocol')
    return {'profile': matched[0], 'pair': pair,
        'request_path': parsed.path + ('?' + parsed.query if parsed.query else '')}


def complete_route(body):
    if (not isinstance(body, dict) or body.get('code') != 'Ok'
            or not isinstance(body.get('routes'), list) or len(body['routes']) != 1
            or not isinstance(body.get('waypoints'), list) or len(body['waypoints']) != 2):
        raise ValueError('Full native OSRM route is unavailable')
    route = body['routes'][0]
    if not isinstance(route, dict) or not {'legs', 'distance', 'duration', 'weight_name', 'weight'} <= route.keys():
        raise ValueError('Incomplete native OSRM route')
    if not isinstance(route['legs'], list) or len(route['legs']) != 1:
        raise ValueError('Unexpected leg count for a two-point route')
    if not isinstance(route['legs'][0].get('steps'), list) or not route['legs'][0]['steps']:
        raise ValueError('Native turn instructions were not captured')
    for name in ('distance', 'duration', 'weight'):
        number = route[name]
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise ValueError('Invalid native numeric route field')
        value = Decimal(str(number))
        if not value.is_finite() or value < 0:
            raise ValueError('Invalid native route numeric value')
    # Entire body and all legs/steps remain retained. Nothing is reduced to
    # merely the visible summary or an arbitrary first highway name.
    fingerprint(body)
    return route


def named_point_matches(query, alternatives, actual_point):
    if not isinstance(alternatives, list) or not alternatives:
        raise ValueError('A named endpoint identity set is empty')
    found = False
    for identity in alternatives:
        record = identity.get('full_geocode_record')
        if (identity.get('requested_query') != query or not isinstance(record, dict)
                or identity.get('full_geocode_sha256') != fingerprint(record)
                or not isinstance(record.get('osm_id'), int) or isinstance(record['osm_id'], bool)
                or record.get('osm_type') not in ('node', 'way', 'relation')
                or not record.get('display_name')):
            raise ValueError('Named identity provenance is incomplete')
        if point(actual_point) == point([record['lat'], record['lon']]):
            found = True
    return found


def endpoint_checks(spec, served):
    request = spec['endpoint_request']
    kind = request['kind']
    actual = served['pair']
    if kind == 'exact_points':
        return {'requested_endpoint_identity': exact_pair(actual, request['pair'])}
    if kind == 'reverse_named_initial_route':
        initial = spec.get('initial_request_pair')
        queries = request.get('initial_queries')
        if (not isinstance(queries, list) or len(queries) != 2
                or not exact_pair(initial, initial)):
            raise ValueError('Original named initial route is required for reversal')
        effective = dict(spec, endpoint_request={'kind': 'named_places', 'queries': list(reversed(queries))})
        checks = endpoint_checks(effective, served)
        checks['original_route_endpoints_reversed'] = exact_pair(actual, list(reversed(initial)))
        return checks
    if kind == 'replace_one_endpoint':
        if (request.get('changed') not in ('origin', 'destination')
                or request.get('unchanged_peer_backend_point_must_remain_exact') is not True
                or not isinstance(request.get('query'), str) or not request['query'].strip()):
            raise ValueError('Original one-endpoint replacement scope is incomplete')
        retained = request.get('retained_pair')
        if not isinstance(retained, str) or len(retained.split(';')) != 2:
            raise ValueError('Exact retained original pair required')
        initial = [point(v.split(',')) for v in retained.split(';')]
        if not exact_pair(spec.get('initial_request_pair'), initial):
            raise ValueError('Initial route differs from the original retained pair')
        index = 0 if request['changed'] == 'origin' else 1
        return {'requested_endpoint_identity': named_point_matches(request['query'], spec.get('replacement_geocode_identities'), actual[index]),
                'unchanged_peer_endpoint_preserved': point(actual[1-index]) == initial[1-index],
                'requested_endpoint_actually_changed': point(actual[index]) != initial[index]}
    if kind == 'named_places':
        identities = spec.get('geocode_identities')
        if not isinstance(identities, list) or len(identities) != 2:
            raise ValueError('Named task lacks independently pinned full geocode identities')
        if len(request['queries']) != 2:
            raise ValueError('Named endpoint declaration is incomplete')
        checks = [named_point_matches(query, alternatives, actual_point)
                  for query, alternatives, actual_point in zip(request['queries'], identities, actual)]
        return {'requested_endpoint_identity': all(checks)}
    raise ValueError('This original endpoint policy still needs its explicit normal contract')


def terminal_checks(spec, served, independently_read_body, native_state, current_url):
    """Terminal-only checks; intermediate wrong objects remain ordinary exploration.

    The full native rendered-content check is supplied by the existing route
    evaluator. A new named identity, source query, or data snapshot cannot be
    accepted by substituting the output of the actor as the private reference.
    """
    actual = complete_route(served['body'])
    independently_read_route = complete_route(independently_read_body)
    if not exact_pair(served['pair'], spec['pinned_request_pair']):
        raise ValueError('Private native reference belongs to a different requested pair')
    checks = endpoint_checks(spec, served)
    checks['requested_transport_mode'] = served['profile'] in spec['allowed_modes']
    checks['actual_backend_complete_and_pinned'] = fingerprint(served['body']) == fingerprint(independently_read_body)
    # Do not interpret a response from a completed previous route as evidence
    # for an unsubmitted edited form: existing route_checks verifies all current
    # visible fields, current URL, full summary/turn rows, loading and line.
    from .map_route_native_display import verified_route_checks
    checks.update(verified_route_checks(spec['rendered_route_spec'], served,
        independently_read_body, native_state, current_url,
        pinned_pair=spec['pinned_request_pair']))
    return checks


class NativeRouteCapture:
    """Passive, complete responses on the real browser context; first error kept."""
    def __init__(self, context, origins, directory):
        self.context = context
        self.origins = dict(origins)
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.responses = []
        self.first_error = None
        self.latest_error = None
        self.attached = True
        self.context.on('response', self._response)

    def _response(self, response):
        parsed = urlsplit(response.url)
        if (parsed.scheme, parsed.netloc) not in {
                (urlsplit(v).scheme, urlsplit(v).netloc) for v in self.origins.values()}:
            return
        try:
            request = native_request(response.url, self.origins)
            if request is None:
                return
            index = len(self.responses)
            data = response.body()
            (self.directory / f'response-{index}.json.body').write_bytes(data)
            row = dict(request, http_status=response.status, bytes=len(data),
                response_sha256=hashlib.sha256(data).hexdigest(), response_index=index,
                artifact_file=f'response-{index}.json.body')
            self.responses.append(row)
            body = json.loads(data)
            if response.status != 200:
                raise ValueError('Native route service returned a non-success status')
            complete_route(body)
            row['body'] = body
            row['complete_native_response'] = True
            self.latest_error = None
        except Exception as error:
            self.latest_error = {'type': type(error).__name__, 'message': str(error), 'actual_url': response.url}
            if self.first_error is None:
                self.first_error = dict(self.latest_error)
        finally:
            (self.directory / 'manifest.json').write_text(json.dumps(
                {'responses': self.responses, 'first_error': self.first_error, 'latest_error': self.latest_error},
                ensure_ascii=False, indent=2, allow_nan=False) + '\n')

    def detach(self):
        if self.attached:
            self.context.remove_listener('response', self._response)
            self.attached = False

    def close(self):
        self.detach()
