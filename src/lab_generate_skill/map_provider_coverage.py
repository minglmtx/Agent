"""Predeclare finite genuine-provider resources; never task success evidence."""
import math
import hashlib
import json
from pathlib import Path
from collections import defaultdict
from urllib.parse import parse_qs, urlsplit

from .source_revision_binding import binding
from .map_provider_contract import validate_resource_family
from .map_route_normal_capture import fingerprint

URLS = {
    'opnv': 'https://tileserver.memomaps.de/tilegen/{z}/{x}/{y}.png',
    'gps': 'https://gps.tile.openstreetmap.org/lines/{z}/{x}/{y}.png',
    'cyclosm': 'https://a.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png',
    'hot': 'https://tile-a.openstreetmap.fr/hot/{z}/{x}/{y}.png',
    'satellite': 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
}


def has_native_initial_fit(candidate):
    """Initialization may fit a route even when retaining it is not the goal."""
    u = urlsplit(candidate['start_path'])
    return (candidate['candidate_completion'].get('retain_initial_route') is True
            or u.path == '/search'
            or (u.path == '/directions' and bool(parse_qs(u.query).get('route'))))


def viewport_tiles(path, viewport, margin_tiles=2):
    fragment = parse_qs(urlsplit(path).fragment, keep_blank_values=True)
    if len(fragment.get('map', [])) != 1:
        raise ValueError('One explicit initial zoom/latitude/longitude required')
    parts = fragment['map'][0].split('/')
    if len(parts) != 3 or not parts[0].isdigit():
        raise ValueError('Complete integer zoom and coordinate pair required')
    zoom = int(parts[0]); lat, lon = map(float, parts[1:])
    if (not 0 <= zoom <= 20 or not all(map(math.isfinite, (lat, lon)))
            or not -85.05112878 <= lat <= 85.05112878 or not -180 <= lon <= 180):
        raise ValueError('Initial view outside WebMercator bounds')
    if (not isinstance(viewport, (list, tuple)) or len(viewport) != 2
            or any(type(v) is not int or not 1 <= v <= 4096 for v in viewport)
            or type(margin_tiles) is not int or not 0 <= margin_tiles <= 3):
        raise ValueError('Bounded explicit viewport and margin required')
    n = 2**zoom
    cx = (lon+180)/360*n
    cy = (1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n
    xs = range(math.floor(cx-viewport[0]/512)-margin_tiles,
               math.ceil(cx+viewport[0]/512)+margin_tiles)
    ys = range(max(0, math.floor(cy-viewport[1]/512)-margin_tiles),
               min(n, math.ceil(cy+viewport[1]/512)+margin_tiles))
    return sorted({(zoom, x % n, y) for x in xs for y in ys})


def captured_initial_view(candidate, record_path, record_sha256):
    """Bind resource coverage to an actual pre-action native route-fit view.

    This does not redefine a task start, use a later actor-selected view, or
    supply task admission. The resulting declaration is frozen with resources.
    """
    raw=Path(record_path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=record_sha256:
        raise ValueError('Native initial-view evidence changed')
    record=json.loads(raw);spec=candidate['candidate_completion']
    if (record.get('source_task_id')!=candidate['source_task_id'] or
        record.get('task_id')!=candidate['task_id'] or record.get('start_path')!=candidate['start_path'] or
        not has_native_initial_fit(candidate)):
        raise ValueError('Same declared route/search task and original start required')
    state=record['initial'];route=record['initial_route']
    from .map_provider_observation import require_initial
    require_initial(candidate,state,route,initial_document=record.get('initial_document'))
    path=f"/#map={state['zoom']}/{state['center']['lat']}/{state['center']['lng']}"
    viewport=[state['size']['x'],state['size']['y']]
    viewport_tiles(path,viewport)
    return dict(source_task_id=candidate['source_task_id'],start_path=candidate['start_path'],
        source_binding_sha256=fingerprint(binding(candidate)),completion_sha256=fingerprint(spec),
        view_path=path,viewport=viewport,evidence=dict(path=str(record_path),sha256=record_sha256),
        reference_phase='native_initial_before_actions',task_start_unchanged=True)


def provider_plans(candidates, existing=None, *, native_initial_views=None):
    existing = existing or {}; combined = defaultdict(set); tasks = defaultdict(list)
    views={}
    for view in native_initial_views or []:
        if view['source_task_id']in views:raise ValueError('Duplicate native initial view')
        views[view['source_task_id']]=view
    seen = set()
    for candidate in candidates:
        source = binding(candidate); spec = candidate['candidate_completion']
        validate_resource_family(spec)
        if (candidate.get('split') != 'train'
                or spec.get('provider') not in URLS or candidate['source_task_id'] in seen):
            raise ValueError('Unique source-bound training base-layer candidate required')
        seen.add(candidate['source_task_id']); provider = spec['provider']
        tiles = viewport_tiles(candidate['start_path'], spec['viewport'])
        native=views.get(candidate['source_task_id'])
        if native is not None:
            if (native.get('start_path')!=candidate['start_path'] or
                native.get('source_binding_sha256')!=fingerprint(source) or
                native.get('completion_sha256')!=fingerprint(spec) or
                native.get('reference_phase')!='native_initial_before_actions' or
                native.get('task_start_unchanged')is not True or not has_native_initial_fit(candidate)):
                raise ValueError('Native initialization resource binding differs')
            tiles=sorted(set(tiles)|set(viewport_tiles(native['view_path'],native['viewport'])))
        combined[provider].update(tiles)
        tasks[provider].append({'source_task_id':candidate['source_task_id'],
            'source_binding_sha256':fingerprint(source), 'start_path':candidate['start_path'],
            'viewport':spec['viewport'], 'tiles':[list(x) for x in tiles]})
    result = {}
    for provider, tiles in combined.items():
        prior = existing.get(provider, {})
        if prior and (prior.get('provider') != provider or prior.get('original_provider_url') != URLS[provider]
                      or prior.get('genuine_provider_bytes') is not True):
            raise ValueError('Existing coverage must bind the same genuine provider')
        covered = {t for t in tiles if '/'.join(map(str,t))+'.png' in prior.get('files', {})}
        result[provider] = {'version':'map18-root-predeclared-provider-coordinate-plan-v1',
            'predeclared_before_actor':True, 'source_tasks':tasks[provider],
            'coverage':{'margin_tiles':2,'arbitrary_pan_or_zoom_covered':False,
                        'browser_coverage_verified':False},
            'reuse_candidates_require_byte_verification':[list(t) for t in sorted(covered)],
            'providers':{provider:{'original_provider_url':URLS[provider],
                                   'tiles':[list(t) for t in sorted(tiles-covered)]}},
            'native_admitted':False}
    return result
