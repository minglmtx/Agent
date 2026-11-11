"""Original Map frontier capability controls, never task admission.

Generic native readers compare real view, form and public API evidence. A
capability positive does not resolve a broad original task's answer scope,
account provenance, named geography or current-view referent.
"""
import math
import re
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

VERSION = 'map-frontier-capabilities-v1'
BOUND_NAMES = ('minlon', 'minlat', 'maxlon', 'maxlat')


def decimal(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError('Native numeric value required')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Native numeric value malformed') from exc
    if not result.is_finite():
        raise ValueError('Finite native value required')
    return result


def bounds(values):
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        raise ValueError('Exactly four native bounds required')
    west, south, east, north = [decimal(v) for v in values]
    if not -180 <= west < east <= 180 or not -85 <= south < north <= 85:
        raise ValueError('Native rectangular area is malformed')
    return tuple(str(v.normalize()) for v in (west, south, east, north))


def area(values):
    west, south, east, north = map(decimal, bounds(values))
    return (east-west)*(north-south)


def form_bounds(panel):
    form = panel.get('export_form') if isinstance(panel, dict) else None
    if not isinstance(form, dict) or form.get('visible') is not True:
        raise ValueError('Visible native Export form required')
    action = urlsplit(form.get('action', ''))
    if (action.path != '/export/finish' or action.scheme or action.netloc or action.query or action.fragment
        or form.get('method', '').lower() != 'post' or form.get('format') != 'osm'):
        raise ValueError('Native OSM Export form identity differs')
    fields = form.get('bounds', {})
    if any(not isinstance(fields.get(n), dict) or fields[n].get('visible') is not True for n in BOUND_NAMES):
        raise ValueError('All current native bounds must be visible')
    return bounds([fields[n]['value'] for n in BOUND_NAMES])


def maximum_area(payload):
    if not isinstance(payload, bytes) or not 1 <= len(payload) <= 1024*1024 or re.search(br'<!DOCTYPE|<!ENTITY', payload, re.I):
        raise ValueError('Bounded native capabilities XML required')
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError('Native capabilities XML malformed') from exc
    rows = root.findall('./api/area')
    if root.tag != 'osm' or len(rows) != 1 or set(rows[0].attrib) != {'maximum'}:
        raise ValueError('Unique native area capability required')
    result = decimal(rows[0].get('maximum'))
    if not 0 < result <= 64800:
        raise ValueError('Native maximum area is unsupported')
    return str(result.normalize())


def native_view(view):
    if not isinstance(view, dict) or view.get('map_visible') is not True:
        raise ValueError('Visible native map required')
    match = re.fullmatch(r'geo:([-+]?\d+(?:\.\d+)?),([-+]?\d+(?:\.\d+)?)\?z=(\d+)', view.get('native_geo_uri', ''))
    if not match:
        raise ValueError('Native geographic map output required')
    lat, lon, zoom = float(match[1]), float(match[2]), int(match[3])
    if not (0 <= zoom <= 20 and math.isfinite(lat) and math.isfinite(lon) and abs(lat) <= 85 and abs(lon) <= 180):
        raise ValueError('Native map output range invalid')
    return zoom, lat, lon


def native_displaced(initial, final):
    a, b = native_view(initial), native_view(final)
    if a[0] != b[0]:
        return False
    # Require over two source-view pixels: coordinate rounding and an editable
    # browser hash do not constitute a meaningful native pan.
    units = 360/(256*2**a[0])
    lon_delta = abs((b[2]-a[2]+180) % 360-180)
    return lon_delta > 2*units or abs(b[1]-a[1]) > 2*units


def relative_zoom(initial, final):
    return native_view(final)[0] > native_view(initial)[0]


def projected_bounds(view, size):
    """Independent EPSG:3857 rectangle from read-only native center and size.

    The native center is rounded by OSM.zoomPrecision. Callers retain that
    bounded uncertainty instead of treating the rounded URL as exact geometry.
    """
    z, lat, lon = native_view(view)
    if set(size) != {'width', 'height'} or any(type(v) is not int or not 256 <= v <= 4096 for v in size.values()):
        raise ValueError('Explicit current native map size required')
    world = 256*2**z
    center_x = (lon+180)/360*world
    sine = math.sin(math.radians(lat))
    center_y = (.5-math.log((1+sine)/(1-sine))/(4*math.pi))*world
    west = (center_x-size['width']/2)/world*360-180
    east = (center_x+size['width']/2)/world*360-180
    south = math.degrees(math.atan(math.sinh(math.pi-2*math.pi*(center_y+size['height']/2)/world)))
    north = math.degrees(math.atan(math.sinh(math.pi-2*math.pi*(center_y-size['height']/2)/world)))
    return tuple(map(str, (west, south, east, north)))


def bounds_match_projection(values, view, size):
    actual, expected = list(map(decimal, bounds(values))), list(map(decimal, bounds(projected_bounds(view, size))))
    z = native_view(view)[0]
    precision = max(0, math.ceil(math.log2(max(1, z))))
    uncertainty = Decimal(2).scaleb(-precision)
    return all(abs(a-b) <= uncertainty for a, b in zip(actual, expected))


def inset_bounds(values, ratio='0.2'):
    west, south, east, north = map(decimal, bounds(values)); ratio = decimal(ratio)
    if not 0 < ratio < Decimal('.5'):
        raise ValueError('Nontrivial native selection inset required')
    x, y = (east-west)*ratio, (north-south)*ratio
    return bounds([west+x, south+y, east-x, north-y])


def selection_checks(initial_bounds, panel, handles, zoom):
    values = form_bounds(panel); initial_bounds = bounds(initial_bounds)
    expected = inset_bounds(initial_bounds)
    tolerance = Decimal(2).scaleb(-max(0, math.ceil(math.log2(max(1, zoom)))))
    form = panel['export_form']
    return {'native_selection_visible': form.get('selection_active') is True and len(handles) >= 4
            and all(h.get('visible') is True and h.get('width', 0) > 0 and h.get('height', 0) > 0 for h in handles),
            'bounds_changed': values != initial_bounds,
            'native_inset_geometry': all(abs(decimal(a)-decimal(b)) <= tolerance for a, b in zip(values, expected))}


def export_checks(panel, max_area, *, require_direct=False):
    values = form_bounds(panel); size = area(values); maximum = decimal(max_area)
    form = panel['export_form']
    checks = {'native_form_ready': panel.get('map_visible') is True,
              'native_limit_relation': form.get('too_large') is (size > maximum)
                and form.get('submit_visible') is (size < maximum)}
    if require_direct:
        checks['native_direct_export_enabled'] = size < maximum and form.get('submit_visible') is True and form.get('too_large') is False
    return checks


def complete_sources(cycles, sources):
    if len(cycles) != 2 or not sources or len(set(sources)) != len(sources):
        return []
    if not cycles[0].get('initial_fingerprint') or cycles[0]['initial_fingerprint'] != cycles[1].get('initial_fingerprint'):
        return []
    keys = ('protected_state_unchanged', 'synthetic_records_unchanged', 'clean_reset_verified', 'dirty_reuse_refused')
    if not all(all(c.get(k) is True for k in keys) for c in cycles):
        return []
    complete = []
    for source in sources:
        rows = [[r for r in cycle.get('sources', []) if r.get('source_task_id') == source] for cycle in cycles]
        if any(len(r) != 1 for r in rows):
            continue
        a, b = rows[0][0], rows[1][0]
        if (a.get('passed') is True and b.get('passed') is True and a.get('reference_signature')
            and a.get('reference_signature') == b.get('reference_signature')
            and a.get('original_first_start') == b.get('original_first_start')):
            complete.append(source)
    return complete


def composite_answer_matches(answer, expected):
    # Capability candidate only: full finite facts are independently extracted
    # from native documents. This is not an open-ended original-task judge.
    return isinstance(answer, dict) and bool(expected) and answer == expected
