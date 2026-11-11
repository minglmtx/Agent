"""Private initial-view references and independent native UI query controls.

Only CPU admission controls navigate to the reference page. Actor scoring uses
the initial task reference, so panning or changing engine cannot redefine it.
"""
import hashlib
import math
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from .site_query_rules import reference_fingerprint


FIELDS = {
    'scale': {'metric_scale': 'string', 'imperial_scale': 'string'},
    'coordinates': {'latitude': 'decimal', 'longitude': 'decimal'},
    'geo_uri': {'geo_uri': 'string'},
    'transport': {'options': 'record_set'},
    'engine': {'engine': 'string'},
}


def initial_view(path):
    u = urlsplit(path)
    if u.scheme or u.netloc or u.path not in ('/', '/directions'):
        raise ValueError('Explicit local native map page required')
    values = parse_qs(u.fragment).get('map', [])
    if len(values) != 1 or not re.fullmatch(r'\d+/[-\d.]+/[-\d.]+', values[0]):
        raise ValueError('Missing initial map coordinates')
    z, lat, lon = values[0].split('/')
    z, lat, lon = int(z), float(lat), float(lon)
    if not (0 <= z <= 20 and math.isfinite(lat) and abs(lat) <= 85 and math.isfinite(lon) and abs(lon) <= 180):
        raise ValueError('Unsupported initial view')
    return z, lat, lon


def scale_labels(zoom, latitude):
    """Leaflet 1.9.4 Control.Scale, default 100px; EPSG:3857 + Earth distance.

    Native pixel rounding can shift the center slightly. Admission separately
    checks the actual displayed labels; it never silently substitutes them.
    """
    if type(zoom) is not int or not 0 <= zoom <= 20 or not math.isfinite(latitude) or abs(latitude) > 85:
        raise ValueError('Unsupported scale position')
    delta = math.radians(360 * 100 / (256 * 2**zoom))
    a = math.cos(math.radians(latitude))**2 * math.sin(delta / 2)**2
    meters = 6371000 * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    def rounded(value):
        p = 10**(len(str(math.floor(value)))-1)
        d = value/p
        return p * next(k for k in (10, 5, 3, 2, 1) if d >= k or k == 1)
    metric = rounded(meters)
    feet = meters * 3.2808399
    return {'metric_scale': f'{metric} m' if metric < 1000 else f'{metric/1000:g} km',
            'imperial_scale': f'{rounded(feet/5280)} mi' if feet > 5280 else f'{rounded(feet)} ft'}


def native_geo_uri(zoom,latitude,longitude):
    """Pinned OSM getGeoUri: fixed zoom-dependent coordinate precision."""
    if (type(zoom) is not int or not 1<=zoom<=20 or
            not all(math.isfinite(v) for v in (latitude,longitude)) or
            abs(latitude)>85 or abs(longitude)>180):
        raise ValueError('Unsupported geographic URI view')
    precision=math.ceil(math.log2(zoom))
    def fixed(value):
        # JS toFixed operates on the actual binary number and breaks exact
        # midpoint ties away from zero; Python format uses ties-to-even.
        number=Decimal.from_float(float(value) if value else 0.0)
        return format(number.quantize(Decimal(1).scaleb(-precision),rounding=ROUND_HALF_UP),'f')
    return f'geo:{fixed(latitude)},{fixed(longitude)}?z={zoom}'


def validate_query(q):
    if q.get('family') != 'map_metadata' or q.get('kind') not in FIELDS or q.get('fields') != FIELDS[q['kind']]:
        raise ValueError('Unsupported map metadata schema')
    initial_view(q['reference_path'])
    if q['kind']=='geo_uri':
        native_geo_uri(*initial_view(q['reference_path']))
        required={'app/assets/javascripts/leaflet.map.js','app/assets/javascripts/osm.js.erb',
                  'app/assets/javascripts/leaflet.share.js','app/assets/javascripts/leaflet.sidebar.js',
                  'app/assets/stylesheets/common.scss'}
        if not required<={r['path'] for r in q.get('source_evidence',[]) if not r.get('installed')}:
            raise ValueError('Geographic URI requires pinned native map/share implementation')
        from .map_share_layout import resized_center
        if q.get('reference_revision') not in ('native-share-layout-v1','initial-map-center-v2'):
            raise ValueError('Geographic URI requires an explicit native Share layout revision')
        resized_center(*initial_view(q['reference_path']),q.get('share_geometry',{}))
    if q['kind'] == 'transport' and q.get('record_fields') != {'options': {'label': 'string'}}:
        raise ValueError('Transport options require complete native labels')
    if q['kind'] in ('engine', 'transport') and urlsplit(q['reference_path']).path != '/directions':
        raise ValueError('Directions query requires native directions page')


def verify_sources(site, q):
    if not q.get('source_evidence'):
        raise ValueError('Missing native implementation reference')
    root = Path(site.root)/'datasets/webarena-map-frontend/openstreetmap-website'
    for row in q['source_evidence']:
        p = Path(row['path'])
        if p.is_absolute() or '..' in p.parts:
            raise ValueError('Invalid native source path')
        base = site.state/'frontend/app' if row['installed'] else root
        if hashlib.sha256((base/p).read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Pinned native metadata implementation changed')


def engine_labels(site):
    root = Path(site.root)/'datasets/webarena-map-frontend/openstreetmap-website'
    sources = sorted((root/'app/assets/javascripts/index/directions').glob('*.js'))
    registrations = []
    for path in sources:
        text = path.read_text()
        matches = re.findall(r'OSM\.Directions\.addEngine\(new FOSSGISOSRMEngine\("([^"]+)", "([^"]+)"\), true\);', text)
        if text.count('OSM.Directions.addEngine(') != len(matches):
            raise ValueError('Unrecognized native routing registration')
        registrations.extend(matches)
    if len(registrations) != 3 or {v for _,v in registrations} != {'car','bike','foot'}:
        raise ValueError('Native routing availability changed')
    locale = (root/'config/locales/en.yml').read_text()
    labels = {}
    for key, _ in registrations:
        values = re.findall(r'^\s+'+re.escape(key)+r': "([^"]+)"$', locale, re.M)
        if len(values) != 1 or key in labels:
            raise ValueError('Missing/ambiguous native engine label')
        labels[key] = values[0]
    return labels


def reference(site, q):
    validate_query(q); verify_sources(site, q)
    z, lat, lon = initial_view(q['reference_path'])
    if q['kind'] == 'scale':
        values = scale_labels(z, lat)
    elif q['kind'] == 'coordinates':
        values = {'latitude': str(lat), 'longitude': str(lon)}
    elif q['kind'] == 'geo_uri':
        from .map_share_layout import resized_center
        center=(z,lat,lon) if q['reference_revision']=='initial-map-center-v2' else resized_center(z,lat,lon,q['share_geometry'])
        values = {'geo_uri':native_geo_uri(*center)}
    else:
        labels = engine_labels(site)
        if q['kind'] == 'transport':
            values = {'options': [{'label': v} for v in sorted(labels.values())]}
        else:
            engines = parse_qs(urlsplit(q['reference_path']).query).get('engine', [])
            if len(engines) != 1 or engines[0] not in labels:
                raise ValueError('Current engine is not bound to the initial directions')
            match = re.fullmatch(r'.+ \(([^()]+)\)', labels[engines[0]])
            if not match:raise ValueError('Unknown engine display format')
            values = {'engine': match[1]}
    return {'object_id': 'map-metadata:'+reference_fingerprint({'kind':q['kind'],'path':q['reference_path']}),
            'values': values, 'reference_source': 'pinned native frontend and original initial state'}


def routing_options(page):
    # Native OSM keeps both responsive search forms in the DOM. Follow the
    # same visible-control rule as read_route; never mix hidden stale options.
    selector=page.locator('select.routing_engines:visible')
    selector.wait_for(state='visible',timeout=10000)
    return selector.locator('option').evaluate_all('es=>es.map(e=>({text:e.textContent.trim(),selected:e.selected}))')


def ui_values(page, q, *, evidence=None):
    """CPU-only independent rendered value capture; no expected values injected."""
    from .map_view import wait_native_view, native_zoom
    validate_query(q)
    origin = urlsplit(page.url)
    if q['kind']=='geo_uri':page.goto('about:blank')
    page.goto(origin.scheme+'://'+origin.netloc+q['reference_path'], wait_until='domcontentloaded', timeout=60000)
    view = wait_native_view(page, q['reference_path'])
    native_zoom(view)
    if q['kind'] == 'scale':
        labels = view['scale']
        metric = [v for v in labels if re.fullmatch(r'\d+(?:\.\d+)? (?:m|km)', v)]
        imperial = [v for v in labels if re.fullmatch(r'\d+(?:\.\d+)? (?:mi|ft)', v)]
        if len(metric) != 1 or len(imperial) != 1:raise ValueError('Native scale lines unavailable')
        values = {'metric_scale': metric[0], 'imperial_scale': imperial[0]}
    elif q['kind'] == 'coordinates':
        match = re.fullmatch(r'geo:([-\d.]+),([-\d.]+)\?z=\d+', view['native_geo_uri'])
        if not match:raise ValueError('Native geographic center unavailable')
        values = dict(zip(('latitude','longitude'), match.groups()))
    elif q['kind'] == 'geo_uri':
        if q['reference_revision']=='initial-map-center-v2':
            # The public browser URL describes the requested initial position.
            # Opening Share changes that position in this native snapshot.
            # Compare the public coordinate representation with the independently
            # generated native link before any such action. The actor can derive
            # this URI from its public URL; no hidden reference enters its input.
            public=urlsplit(page.url)
            public_path=public.path+('#'+public.fragment if public.fragment else '')
            geo=view['native_geo_uri']
            if native_geo_uri(*initial_view(public_path))!=geo:
                raise ValueError('Public map coordinates disagree with native geographic URI')
            values={'geo_uri':geo}
            if evidence is not None:evidence.append({'url':page.url,'native_view':view,'values':values,
                'observation_basis':'Public initial URL coordinates and independently generated native Geo URI; no Share-induced pan.'})
            return values
        # CPU admission only: ensure the value is actually readable through the
        # public Share UI, not merely present in a hidden element or private JS.
        from .map_share_layout import open_verified_share
        open_verified_share(page,q['share_geometry'])
        link=page.locator('.share-ui #geo_uri:visible')
        link.wait_for(state='visible',timeout=10000)
        text=link.inner_text().strip()
        if text!=link.get_attribute('href') or not re.fullmatch(r'geo:[-\d.]+,[-\d.]+\?z=\d+',text):
            raise ValueError('Native geographic URI is missing or inconsistent')
        values={'geo_uri':text}
    else:
        options = routing_options(page)
        if q['kind'] == 'transport':values = {'options':[{'label':o['text']}for o in options]}
        else:
            selected = [o['text']for o in options if o['selected']]
            if len(selected) != 1:raise ValueError('Current engine unavailable')
            match = re.fullmatch(r'.+ \(([^()]+)\)', selected[0])
            if not match:raise ValueError('Unknown native engine label')
            values = {'engine':match[1]}
    if evidence is not None:evidence.append({'url':page.url,'native_view':view,'values':values})
    return values
