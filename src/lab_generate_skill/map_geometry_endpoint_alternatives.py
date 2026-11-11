"""Explicit endpoint alternatives backed by native semantics and geometry.

This supplements missing identity tags; it does not treat containment alone as
identity, equate coordinates, grant admission, or change existing declarations.
Unsupported geometry/ambiguous groups remain unresolved.
"""
from copy import deepcopy
from decimal import Decimal
import re

from .map_native_identity_declarations import declare_query, normalized
from .map_place_geometry_evidence import bind_geometry
from .map_route_normal_capture import fingerprint


def xy(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError('Two-dimensional native geometry required')
    try:
        point = tuple(Decimal(str(v)) for v in value)
    except Exception as exc:
        raise ValueError('Finite native coordinates required') from exc
    if (not all(v.is_finite() for v in point) or abs(point[0]) > 180 or abs(point[1]) > 90):
        raise ValueError('Finite longitude/latitude required')
    return point


def ring_position(point, ring):
    """Ray crossing with explicit boundary rejection; Decimal avoids epsilon expansion."""
    if not isinstance(ring, list) or not 4 <= len(ring) <= 10000:
        raise ValueError('Bounded complete polygon ring required')
    points = [xy(v) for v in ring]
    if points[0] != points[-1] or len(set(points[:-1])) < 3:
        raise ValueError('Closed nondegenerate ring required')
    if max(v[0] for v in points)-min(v[0] for v in points) >= 180:
        raise ValueError('Antimeridian geometry needs a separate reviewed implementation')
    x, y = xy(point)
    inside = False
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        cross = (x-ax)*(by-ay)-(y-ay)*(bx-ax)
        if cross == 0 and min(ax,bx) <= x <= max(ax,bx) and min(ay,by) <= y <= max(ay,by):
            return 'boundary'
        if (ay > y) != (by > y) and x < ax+(y-ay)*(bx-ax)/(by-ay):
            inside = not inside
    return 'inside' if inside else 'outside'


def strictly_contained(point, geometry):
    if geometry.get('type') != 'Polygon':
        raise ValueError('This reviewed protocol requires one Polygon')
    rings = geometry.get('coordinates')
    if not isinstance(rings, list) or not 1 <= len(rings) <= 100:
        raise ValueError('Complete bounded polygon rings required')
    return (ring_position(point, rings[0]) == 'inside'
            and all(ring_position(point, hole) == 'outside' for hole in rings[1:]))


def pair_checks(query, area, point):
    a, b = area.get('address', {}), point.get('address', {})
    required_address = {'house_number', 'road', 'postcode', 'country_code', 'state'}
    ae, pe = area.get('extratags', {}), point.get('extratags', {})
    anchors = {'wikidata', 'wikipedia'}
    anchor_valid = (bool(re.fullmatch(r'Q[1-9][0-9]*', str(ae.get('wikidata', ''))))
                    and isinstance(ae.get('wikipedia'), str) and ':' in ae['wikipedia'])
    same_name = lambda r: normalized(r.get('namedetails', {}).get('name')) == normalized(query)
    geometry = point.get('geojson', {})
    coordinates = geometry.get('coordinates')
    identity = (area.get('osm_type'), area.get('osm_id')) != (point.get('osm_type'), point.get('osm_id'))
    try:
        contained = (geometry.get('type') == 'Point'
                     and xy(coordinates) == xy([point['lon'], point['lat']])
                     and strictly_contained(coordinates, area.get('geojson', {})))
    except (ValueError, KeyError, TypeError):
        contained = False
    return dict(distinct_native_objects=identity,
                same_declared_name=same_name(area) and same_name(point),
                same_feature_kind=(area.get('category'),area.get('type')) == (point.get('category'),point.get('type')),
                exact_complete_address=isinstance(a,dict) and a == b and required_address <= a.keys()
                    and all(isinstance(a.get(k),str) and a[k].strip() for k in required_address),
                anchored_area=anchor_valid,
                no_contradictory_identity=all(k not in pe or pe[k] == ae.get(k) for k in anchors),
                point_strictly_in_area=contained)


def declare_geometry_alternatives(native, receipt, raw_body):
    geometry = bind_geometry(native, receipt, raw_body)
    review = declare_query(native['query'], native)
    if review.get('status') != 'ambiguous_native_identity' or review.get('matching_native_record_count') != 2:
        raise ValueError('Exactly two independently matching semantic records required')
    accepted = [r['full_geocode_record'] for r in review['all_native_record_checks']
                if all(r['checks'].values())]
    keys = {(r['osm_type'],r['osm_id']) for r in accepted}
    enriched = [r['full_record'] for r in geometry['objects'] if (r['osm_type'],r['osm_id']) in keys]
    areas = [r for r in enriched if r['geojson']['type'] == 'Polygon']
    points = [r for r in enriched if r['geojson']['type'] == 'Point']
    if len(areas) != 1 or len(points) != 1:
        raise ValueError('One semantic area and one semantic point required')
    checks = pair_checks(native['query'], areas[0], points[0])
    if not all(checks.values()):
        raise ValueError('Native semantics/geometry do not establish acceptable endpoint alternatives: '+str(checks))
    return dict(version='native-named-point-area-alternatives-v1', query=native['query'],
                checks=checks, full_native_query_review=review, geometry_evidence=geometry,
                alternatives=[dict(point=[r['lat'],r['lon']], identities=[deepcopy(r)],
                    kind='declared_native_named_point_or_area', provider_rank_used=False,
                    normal_admission=False) for r in enriched],
                accepted_native_objects=sorted([list(k) for k in keys]),
                coordinates_claimed_equal=False, polygons_claimed_equal=False,
                actor_or_later_published_step_used=False, selected_osm_id=None,
                evidence_sha256=fingerprint(geometry), normal_admission=False)


def replacement_variants(candidate, native, receipt, raw_body):
    """Keep the publicly declared origin/mode; vary only supported destinations."""
    from .map_route_candidate_batch import backend_spec
    from .map_route_normal_capture import point
    spec = backend_spec(candidate)
    request = spec['endpoint_request']
    if (request.get('kind') != 'replace_one_endpoint' or request.get('changed') != 'destination'
            or request.get('query') != native.get('query')):
        raise ValueError('Explicit bound destination replacement required')
    initial = [point(p.split(',')) for p in request['retained_pair'].split(';')]
    if len(initial) != 2 or initial[0] != point(request['preserved_origin']):
        raise ValueError('Original route and preserved origin differ')
    declaration = declare_geometry_alternatives(native, receipt, raw_body)
    variants = []
    for endpoint in declaration['alternatives']:
        if point(endpoint['point']) in initial:
            raise ValueError('Replacement must change the destination without a degenerate route')
        variants.append(dict(pair=[[str(v) for v in initial[0]], endpoint['point']],
            initial_pair=[[str(v) for v in p] for p in initial],
            scope=request['source'], initialization_revision=deepcopy(spec['initialization_revision']),
            endpoint_geometry_declaration_sha256=fingerprint(declaration),
            normal_admission=False, provider_rank_used=False))
    return spec, variants, declaration
