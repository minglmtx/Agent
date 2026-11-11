"""Scoped local tile transport and reversible native provider installation.

No network capture, task action, database initialization or success claim.
Resource materialization independently validates upstream pixel provenance.
This serves those immutable bytes and reads actual Leaflet state privately.
"""
from collections import Counter
from copy import deepcopy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit
import math

from .map_native_layer_runtime import MAP_CONSTRUCTOR
from .owned_file_edits import OwnedFileEdits
from .map_provider_contract import PROVIDER_CODES, TILE_PROVIDER_CODES


VERSION = 'map-frozen-provider-transport-v1'
READER = r'''
  Object.defineProperty(window, "__labFrozenProviderState", {
    configurable: false, writable: false,
    value: function () {
      return {zoom: map.getZoom(), center: map.getCenter(),
        bounds: map.getBounds().toBBoxString(), size: map.getSize(),
        active: map.baseLayers.filter(x => map.hasLayer(x)).map(x => ({
          code: x.options.code, name: x.options.name, template: x._url,
          tiles: Object.values(x._tiles || {}).map(t => {
            var r = t.el.getBoundingClientRect(), m = map.getContainer().getBoundingClientRect();
            return {src: t.el.currentSrc || t.el.src, coords: t.coords,
              loaded: t.el.complete && t.el.naturalWidth === 256 && t.el.naturalHeight === 256,
              current: t.current === true,
              rect: [Math.max(0,r.left-m.left),Math.max(0,r.top-m.top),
                     Math.min(m.width,r.right-m.left),Math.min(m.height,r.bottom-m.top)]};
          })}))};
    }
  });
'''

# Keep GPS in the native overlay pane. This reader only exposes observed state;
# it does not turn the layer on, move the map, or establish task admission.
GPS_READER = r'''
  Object.defineProperty(window, "__labFrozenGPSState", {
    configurable: false, writable: false,
    value: function () {
      return {zoom: map.getZoom(), center: map.getCenter(),
        bounds: map.getBounds().toBBoxString(), size: map.getSize(),
        enabled: map.hasLayer(map.gpsLayer), code: map.gpsLayer.options.code,
        template: map.gpsLayer._url,
        tiles: Object.values(map.gpsLayer._tiles || {}).map(t => {
          var r = t.el.getBoundingClientRect(), m = map.getContainer().getBoundingClientRect();
          return {src: t.el.currentSrc || t.el.src, coords: t.coords,
            loaded: t.el.complete && t.el.naturalWidth === 256 && t.el.naturalHeight === 256,
            current: t.current === true,
            rect: [r.left-m.left,r.top-m.top,r.right-m.left,r.bottom-m.top]};
        })};
    }
  });
'''


GPS_DOCUMENT_READER = GPS_READER.replace(
    'return {zoom:',
    'return {map_visible: !!map.getContainer().getClientRects().length, loading: map.gpsLayer._loading === true, zoom:')


def patched_sources(sources, origin, providers, *, gps_document=False):
    if type(gps_document) is not bool or (gps_document and set(providers) != {'gps'}):
        raise ValueError('GPS document observation requires its dedicated GPS provider')
    parsed = urlsplit(origin)
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port
            or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment
            or not providers or set(providers) - set(TILE_PROVIDER_CODES)):
        raise ValueError('Owned local provider origin and explicit supported providers required')
    result = deepcopy(sources)
    tile = result['vendor/assets/leaflet/leaflet.osm.js']
    if 'gps' in providers:
        old = 'https://gps.tile.openstreetmap.org/lines/'
        if tile.count(old) != 1: raise ValueError('Pinned native GPS source changed')
        tile = tile.replace(old, origin + '/tiles/gps/')
    if 'hot' in providers:
        old = 'https://tile-{s}.openstreetmap.fr/hot/'
        if tile.count(old) != 1: raise ValueError('Pinned native HOT source changed')
        tile = tile.replace(old, origin + '/tiles/hot/')
    if 'cyclosm' in providers:
        old = 'https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm/'
        if tile.count(old) != 1: raise ValueError('Pinned native CyclOSM source changed')
        tile = tile.replace(old, origin + '/tiles/cyclosm/')
    if 'opnv' in providers:
        old = 'https://tileserver.memomaps.de/tilegen/'
        layer = result['app/assets/javascripts/leaflet.map.js']
        import re
        native = re.search(r'new L\.OSM\.OPNVKarte\(\{(?P<body>.*?)\}\)', layer, re.S)
        if (tile.count(old) != 1 or native is None
                or not re.search(r'code:\s*[\"\']O[\"\']', native['body'])
                or not re.search(r'keyid:\s*[\"\']opnvkarte[\"\']', native['body'])):
            raise ValueError('Pinned native public-transport provider identity changed')
        tile = tile.replace(old, origin + '/tiles/opnv/')
    if 'satellite' in providers:
        if 'L.OSM.LocalFrozenSatellite' in tile: raise ValueError('Provider already installed')
        # L.OSM.TileLayer.initialize reads options.url, not a top-level url.
        tile += '\nL.OSM.LocalFrozenSatellite=L.OSM.TileLayer.extend({options:{url:' + json.dumps(
            origin + '/tiles/satellite/{z}/{x}/{y}.png') + ',maxZoom:20}});\n'
        name = 'app/assets/javascripts/leaflet.map.js'
        anchor = '    this.noteLayer = new L.FeatureGroup();'
        if result[name].count(anchor) != 1: raise ValueError('Pinned native catalog changed')
        result[name] = result[name].replace(anchor,
            '    this.baseLayers.push(new L.OSM.LocalFrozenSatellite({code:"S",keyid:"satellite",name:"Satellite"}));\n' + anchor)
    result['vendor/assets/leaflet/leaflet.osm.js'] = tile
    name = 'app/assets/javascripts/index.js'
    if (result[name].count(MAP_CONSTRUCTOR) != 1 or '__labFrozenProviderState' in result[name]
            or '__labFrozenGPSState' in result[name]):
        raise ValueError('Pinned native constructor changed or reader already installed')
    result[name] = result[name].replace(MAP_CONSTRUCTOR, MAP_CONSTRUCTOR + READER
        + ((GPS_DOCUMENT_READER if gps_document else GPS_READER) if 'gps' in providers else ''))
    return result


SOURCE_FILES = ('vendor/assets/leaflet/leaflet.osm.js',
                'app/assets/javascripts/leaflet.map.js', 'app/assets/javascripts/index.js')


class FrozenProviderServer:
    """One in-memory, hash-checked tile set per worker; no per-request files."""
    def __init__(self, materialized, root):
        root = Path(root).resolve()
        specs = materialized['assets']['frozen_tile_providers']
        if not specs or set(specs) - set(TILE_PROVIDER_CODES):
            raise ValueError('Explicit supported provider assets required')
        self.bodies = {}; self.receipts = Counter(); self.lock = threading.Lock()
        self.providers = sorted(specs); self.closed = False
        total_bytes = 0
        for provider, spec in specs.items():
            if spec.get('genuine_provider_bytes') is not True or spec.get('provider') != provider:
                raise ValueError('Genuine named provider required')
            for key, row in spec['files'].items():
                relative = f'assets/providers/{provider}/tiles/{key}'
                path = root / relative
                if (row['member'] != relative or '..' in Path(key).parts
                        or path.is_symlink() or not path.resolve().is_relative_to(root)):
                    raise ValueError('Owned provider tile path required')
                data = path.read_bytes()
                total_bytes += len(data)
                if total_bytes > 256 * 1024**2: raise ValueError('Provider memory budget exceeded')
                if len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
                    raise ValueError('Materialized tile bytes changed')
                self.bodies['/tiles/' + provider + '/' + key] = data
        if not self.bodies or sum(map(len, self.bodies.values())) > 256 * 1024**2:
            raise ValueError('Provider memory budget exceeded or empty tile set')
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup(); self.connection.settimeout(5)
            def log_message(self, *_): pass
            def do_GET(self):
                data = owner.bodies.get(self.path)
                status = 200 if data is not None else 404
                with owner.lock: owner.receipts[(self.path if data is not None else 'unknown', status)] += 1
                body = data if data is not None else b'Frozen provider coordinate unavailable'
                self.send_response(status)
                self.send_header('Content-Type', 'image/png' if data is not None else 'text/plain')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers(); self.wfile.write(body)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = False
        self.url = 'http://127.0.0.1:' + str(self.server.server_address[1])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=False)
        self.thread.start()

    def snapshot(self):
        with self.lock:
            rows = [dict(path=p, status=s, count=n,
                sha256=hashlib.sha256(self.bodies[p]).hexdigest() if p in self.bodies else None)
                for (p, s), n in sorted(self.receipts.items())]
        return dict(version=VERSION, requests=rows, tiles=len(self.bodies),
                    bytes=sum(map(len, self.bodies.values())), closed=self.closed)

    def close(self):
        if self.closed: return
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=10)
        if self.thread.is_alive(): raise RuntimeError('Owned provider transport still running')
        self.closed = True


class NativeProviderExtension:
    """Only modify the owned frontend; restore before it can serve another profile."""
    def __init__(self, site, server, *, gps_document=False):
        self.gps_document = gps_document
        self.site, self.server = site, server
        self.app = site.state / 'frontend/app'
        self.edits = OwnedFileEdits(self.app)
        self.netloc = urlsplit(server.url).netloc
        if self.netloc in site.allowed_netlocs: raise ValueError('Provider origin already owned')
        self.installed = False

    def install(self):
        originals = {name: (self.app / name).read_text() for name in SOURCE_FILES}
        patched = patched_sources(originals, self.server.url, self.server.providers, gps_document=self.gps_document)
        try:
            for name, text in patched.items(): self.edits.write_text(self.app / name, text)
            self.site.allowed_netlocs = tuple(self.site.allowed_netlocs) + (self.netloc,)
            self.site.restart_frontend(preserve_compiled_assets=False)
            self.installed = True
        except BaseException:
            self.site._reuse_invalid_reason = 'Frozen provider installation incomplete'
            self.close()
            raise
        return dict(version=VERSION, original_snapshot_equivalence=False,
            files={n: dict(before=hashlib.sha256(originals[n].encode()).hexdigest(),
                           after=hashlib.sha256(patched[n].encode()).hexdigest()) for n in originals},
            external_requests_required=False, automatic_task_actions=0)

    def close(self):
        try:
            receipt = self.edits.restore()
            self.site._frontend_assets_changed = True
            self.site.allowed_netlocs = tuple(x for x in self.site.allowed_netlocs if x != self.netloc)
            self.installed = False
            return receipt
        except BaseException:
            self.site._reuse_invalid_reason = 'Frozen provider source restoration failed'
            raise


def covered_area(rectangles, width, height):
    """Exact rectangle union, avoiding counts that accept overlapping tiles."""
    clipped = []
    for rect in rectangles:
        if len(rect) != 4 or any(not math.isfinite(v) for v in rect): return 0
        a, b, c, d = rect
        a, b, c, d = max(0, a), max(0, b), min(width, c), min(height, d)
        if a < c and b < d: clipped.append((a, b, c, d))
    xs = sorted({x for r in clipped for x in (r[0], r[2])}); area = 0
    for left, right in zip(xs, xs[1:]):
        spans = sorted((b, d) for a, b, c, d in clipped if a <= left and c >= right)
        end = 0; length = 0
        for bottom, top in spans:
            length += max(0, top - max(bottom, end)); end = max(end, top)
        area += (right - left) * length
    return area


def same_view(initial, terminal):
    """Permit native sidebar resize, but neither geographic pan nor zoom."""
    if initial['zoom'] != terminal['zoom']: return False
    world = 256 * 2**initial['zoom']
    def point(state):
        lat, lon = state['center']['lat'], state['center']['lng']
        if not all(map(math.isfinite, (lat, lon))) or abs(lat) > 85.05112878: raise ValueError('Invalid center')
        return ((lon+180)/360*world, (1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*world)
    x, y = point(initial); a, b = point(terminal)
    centered = abs(x-a) <= 1 and abs(y-b) <= 1
    same_origin = (abs(x-initial['size']['x']/2-a+terminal['size']['x']/2) <= 1
                   and abs(y-initial['size']['y']/2-b+terminal['size']['y']/2) <= 1)
    return centered or same_origin


def provider_checks(initial, terminal, provider, server, response_hashes):
    """Private terminal evidence only; no hidden targets sent to an actor."""
    checks = dict(native_requested_layer=False, same_initial_area=False,
                  loaded_genuine_tiles=False, complete_visible_coverage=False)
    try:
        expected = PROVIDER_CODES[provider]
        active = terminal['active']
        checks['same_initial_area'] = same_view(initial, terminal)
        if len(active) != 1 or active[0]['code'] != expected: return checks
        layer = active[0]
        checks['native_requested_layer'] = layer['template'] == server.url + '/tiles/' + provider + '/{z}/{x}/{y}.png'
        rects = []; all_valid = True; count = 0
        for tile in layer['tiles']:
            a, b, c, d = tile['rect']
            if not tile['current'] or c <= a or d <= b: continue
            count += 1; u = urlsplit(tile['src']); coords = tile['coords']
            path = f'/tiles/{provider}/{coords["z"]}/{coords["x"]}/{coords["y"]}.png'
            valid = (tile['loaded'] is True and u.scheme == 'http'
                and u.netloc == urlsplit(server.url).netloc and not u.query and not u.fragment
                and u.path == path and path in server.bodies
                and response_hashes.get(tile['src']) == hashlib.sha256(server.bodies[path]).hexdigest())
            all_valid = all_valid and valid
            if valid: rects.append(tile['rect'])
        checks['loaded_genuine_tiles'] = count > 0 and all_valid
        width, height = terminal['size']['x'], terminal['size']['y']
        checks['complete_visible_coverage'] = (width > 0 and height > 0
            and covered_area(rects, width, height) >= width * height - 1)
    except (KeyError, TypeError, ValueError, OverflowError): pass
    return checks
