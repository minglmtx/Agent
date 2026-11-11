"""Inspect actual native OSM XML attachments; this helper grants no admission.

Reference geometry comes from the current disposable native database. A second
same-origin API request supplies an independent transport/reference for all
native way/relation expansion. No renderer, task target or actor action is added.
"""
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlsplit
import xml.etree.ElementTree as ET

VERSION = 'map-native-osm-artifact-capability-v1'
MAX_BYTES = 32 * 1024 * 1024
MAX_OBJECTS = 100000
COORD_NAMES = ('minlon', 'minlat', 'maxlon', 'maxlat')


def coordinate(value):
    if isinstance(value, bool):
        raise ValueError('Boolean is not an OSM coordinate')
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError('Malformed OSM coordinate') from None
    if not result.is_finite():
        raise ValueError('Non-finite OSM coordinate')
    if abs(result) > 180:
        raise ValueError('Coordinate exceeds the native geographic range')
    if result != result.quantize(Decimal('0.0000001')):
        raise ValueError('Coordinate exceeds native OSM precision')
    return format(result.normalize(), 'f') if result else '0'


def bbox(values):
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        raise ValueError('Four native export bounds required')
    result = tuple(coordinate(v) for v in values)
    west, south, east, north = map(Decimal, result)
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError('Invalid native export rectangle')
    return result


def bbox_area(values):
    west, south, east, north = map(Decimal, bbox(values))
    return (east - west) * (north - south)


def form_bbox(state):
    form = state.get('export_form') if isinstance(state, dict) else None
    if not isinstance(form, dict) or form.get('visible') is not True:
        raise ValueError('Native Export form unavailable')
    fields = form.get('bounds', {})
    if any(not isinstance(fields.get(n), dict) or fields[n].get('visible') is not True for n in COORD_NAMES):
        raise ValueError('Native bounds are not displayed')
    return bbox([fields[n]['value'] for n in COORD_NAMES])


def positive_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[1-9]\d*', value):
        raise ValueError('Invalid native OSM object identifier')
    return value


def parse_xml(payload):
    if not isinstance(payload, bytes) or not 1 <= len(payload) <= MAX_BYTES:
        raise ValueError('OSM attachment exceeds inspection budget or is empty')
    upper = payload.upper()
    if b'<!DOCTYPE' in upper or b'<!ENTITY' in upper:
        raise ValueError('OSM attachment must not contain document entities')
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        raise ValueError('Malformed OSM XML attachment') from None
    if root.tag != 'osm' or root.attrib.get('version') != '0.6':
        raise ValueError('Expected native OSM 0.6 export')
    if len(root) > MAX_OBJECTS + 1:
        raise ValueError('Too many native OSM objects')
    bound_elements = root.findall('bounds')
    if len(bound_elements) != 1:
        raise ValueError('One native export bounds element required')
    bounds = bbox([bound_elements[0].attrib.get(n) for n in COORD_NAMES])
    objects = {kind: {} for kind in ('node', 'way', 'relation')}
    for element in root:
        kind = element.tag
        if kind == 'bounds':
            continue
        if kind not in objects:
            raise ValueError('Unexpected native OSM export element')
        ident = positive_id(element.attrib.get('id'))
        if ident in objects[kind]:
            raise ValueError('Duplicate native OSM object')
        value = {'version': positive_id(element.attrib.get('version')), 'attributes': dict(element.attrib), 'tags': {}}
        if kind == 'node':
            lat, lon = coordinate(element.attrib.get('lat')), coordinate(element.attrib.get('lon'))
            if not (-90 <= Decimal(lat) <= 90 and -180 <= Decimal(lon) <= 180):
                raise ValueError('Native node outside coordinate range')
            value.update(lat=lat, lon=lon)
        elif kind == 'way':
            value['nodes'] = []
        else:
            value['members'] = []
        for child in element:
            if child.tag == 'tag':
                key, val = child.attrib.get('k'), child.attrib.get('v')
                if not isinstance(key, str) or not key or not isinstance(val, str) or key in value['tags']:
                    raise ValueError('Malformed or duplicate native OSM tag')
                value['tags'][key] = val
            elif child.tag == 'nd' and kind == 'way':
                value['nodes'].append(positive_id(child.attrib.get('ref')))
            elif child.tag == 'member' and kind == 'relation':
                member_type = child.attrib.get('type')
                if member_type not in objects or not isinstance(child.attrib.get('role'), str):
                    raise ValueError('Malformed native relation member')
                value['members'].append({'type': member_type, 'ref': positive_id(child.attrib.get('ref')), 'role': child.attrib['role']})
            else:
                raise ValueError('Unexpected native OSM object child')
        objects[kind][ident] = value
    for way in objects['way'].values():
        if not way['nodes'] or any(n not in objects['node'] for n in way['nodes']):
            raise ValueError('Native export way lacks referenced nodes')
    canonical = {'bounds': bounds, 'root_attributes': dict(root.attrib), 'objects': objects}
    signature = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    west, south, east, north = map(Decimal, bounds)
    inside = {ident: {'lat': item['lat'], 'lon': item['lon']} for ident, item in objects['node'].items()
              if west <= Decimal(item['lon']) <= east and south <= Decimal(item['lat']) <= north}
    return {'bounds': bounds, 'signature': signature, 'in_bbox_nodes': inside,
            'counts': {kind: len(value) for kind, value in objects.items()}}


def geometry_reference(value, bounds):
    bounds = bbox(bounds)
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_OBJECTS:
        raise ValueError('Independent native geometry must contain bounded nodes')
    result = {}
    west, south, east, north = map(Decimal, bounds)
    for row in value:
        if not isinstance(row, dict):
            raise ValueError('Malformed native geometry reference')
        ident = positive_id(str(row.get('id')))
        lat, lon = coordinate(row.get('lat')), coordinate(row.get('lon'))
        if ident in result or not (west <= Decimal(lon) <= east and south <= Decimal(lat) <= north):
            raise ValueError('Duplicate or out-of-bounds native reference node')
        result[ident] = {'lat': lat, 'lon': lon}
    return result


def make_reference(payload, bounds, native_nodes):
    bounds = bbox(bounds); parsed = parse_xml(payload); nodes = geometry_reference(native_nodes, bounds)
    if parsed['bounds'] != bounds or parsed['in_bbox_nodes'] != nodes:
        raise ValueError('Native API payload differs from independent database geometry')
    return {'bounds': bounds, 'signature': parsed['signature'], 'in_bbox_nodes': nodes,
            'counts': parsed['counts'], 'native_database_geometry_verified': True,
            'independent_transport': 'same_origin_api_reference_then_native_browser_form_download'}


def request_bbox(url, site_origin):
    actual, expected = urlsplit(url), urlsplit(site_origin)
    if actual.scheme not in ('http', 'https') or (actual.scheme, actual.netloc) != (expected.scheme, expected.netloc):
        raise ValueError('OSM attachment source is not the local task origin')
    if actual.username is not None or actual.password is not None or actual.path != '/api/0.6/map' or actual.fragment:
        raise ValueError('Expected the native map API attachment path')
    query = parse_qs(actual.query, keep_blank_values=True, strict_parsing=True)
    if set(query) != {'bbox'} or len(query['bbox']) != 1:
        raise ValueError('One native bbox parameter required')
    return bbox(query['bbox'][0].split(','))


def artifact_checks(record, payload, reference, site_origin):
    checks = {'download_completed': False, 'native_attachment_response': False,
              'correct_native_bounds': False, 'valid_nonempty_osm': False,
              'native_geometry_matches': False, 'native_full_payload_matches': False}
    if not isinstance(record, dict) or record.get('status') != 'completed':
        return checks
    checks['download_completed'] = True
    try:
        bounds = request_bbox(record.get('url', ''), site_origin)
        content_type = record.get('content_type', '').split(';', 1)[0].strip().lower()
        disposition = record.get('content_disposition', '')
        checks['native_attachment_response'] = (record.get('http_status') == 200 and content_type in ('application/xml', 'text/xml')
                                                and bool(re.match(r'attachment\s*;', disposition, re.I)))
        checks['correct_native_bounds'] = bounds == bbox(reference['bounds'])
        actual = parse_xml(payload)
        checks['valid_nonempty_osm'] = bool(actual['in_bbox_nodes']) and actual['counts']['node'] > 0
        checks['correct_native_bounds'] &= actual['bounds'] == bbox(reference['bounds'])
        checks['native_geometry_matches'] = (reference.get('native_database_geometry_verified') is True and
                                              actual['in_bbox_nodes'] == reference['in_bbox_nodes'])
        checks['native_full_payload_matches'] = actual['signature'] == reference['signature']
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    return checks


def passed(record, payload, reference, site_origin):
    return all(artifact_checks(record, payload, reference, site_origin).values())
