"""Private, read-only inspection of independently reopened sharing artifacts.

This supplements URL/markup checks; it neither executes task actions nor
admits a task. Initial references must be captured before the actor runs.
"""
import math
from .map_frozen_provider_runtime import covered_area
from .map_local_capabilities import same_center
from .map_share_artifact_checks import route_link, view_link

READER = r'''
  Object.defineProperty(window, "__labShareState", {value: function () {
    var box=map.getContainer().getBoundingClientRect(), layers=[];
    map.eachLayer(function(layer) {
      if (!layer._url) return;
      layers.push({template:layer._url, tiles:Object.values(layer._tiles||{}).map(function(t) {
        var r=t.el.getBoundingClientRect();
        return {current:t.current===true, loaded:t.el.complete&&t.el.naturalWidth===256&&t.el.naturalHeight===256,
          src:t.el.currentSrc||t.el.src,
          rect:[Math.max(0,r.left-box.left),Math.max(0,r.top-box.top),Math.min(box.width,r.right-box.left),Math.min(box.height,r.bottom-box.top)]};
      })});
    });
    return {zoom:map.getZoom(),center:map.getCenter(),bounds:map.getBounds().toBBoxString(),
      size:{width:map.getSize().x,height:map.getSize().y},layers:layers};
  }, writable:false, configurable:false});
'''


def patch_readers(sources):
    from .map_native_layer_runtime import MAP_CONSTRUCTOR
    out = dict(sources)
    for name, anchor in (
        ('app/assets/javascripts/index.js', MAP_CONSTRUCTOR),
        ('app/assets/javascripts/embed.js.erb', '  var map = L.map("map");'),
    ):
        if out[name].count(anchor) != 1 or '__labShareState' in out[name]:
            raise ValueError('Original native map constructor changed or observer already installed')
        out[name] = out[name].replace(anchor, anchor + READER)
    return out


def rendered_standard(state, tile_origin):
    """Require the real local Standard provider and complete decoded viewport."""
    from urllib.parse import urlsplit
    try:
        layers = state['layers']
        if len(layers) != 1 or layers[0]['template'] != tile_origin + '/tile/{z}/{x}/{y}.png':
            return False
        width, height = state['size']['width'], state['size']['height']
        if min(width, height) <= 0: return False
        rects = []
        for t in layers[0]['tiles']:
            a,b,c,d = t['rect']
            if not t['current'] or c<=a or d<=b: continue
            u=urlsplit(t['src'])
            if not t['loaded'] or u.netloc!=urlsplit(tile_origin).netloc or not u.path.startswith('/tile/'):
                return False
            rects.append(t['rect'])
        return covered_area(rects,width,height) >= width*height-1
    except (ValueError,TypeError,KeyError): return False


def reopened_route(value, state, initial_route, *, origin, expected_pair, expected_mode):
    from .map_route import parse_point, pair_equal
    def endpoints(record):
        return [parse_point(record.get(k)) for k in ('origin','destination')]
    declared = [[float(v) for v in point] for point in expected_pair]
    return dict(
        explicit_route=route_link(value, origin=origin, expected_pair=expected_pair, expected_mode=expected_mode),
        rendered_route=state.get('route_visible') is True and state.get('loading') is False and bool(state.get('rows')),
        original_route_content=bool(initial_route.get('rows')) and
        pair_equal(endpoints(initial_route), declared) and pair_equal(endpoints(state), declared) and all(
            state.get(k)==initial_route.get(k) for k in ('engine','rows')))


def warm_reopened_tiles(page, tile_origin, report, *, seconds=180):
    """Prepare only the displayed native tiles, preserving map geometry.

    A cold mod_tile 404 can precede successful rendering. Reuse bounded native
    warming and retry failed images only after their real PNGs are available.
    Works for both the main page and a genuine embedded map frame.
    """
    from urllib.parse import urlsplit
    from .map_tile_warmup import warm_tiles, tile_path
    read = lambda: page.evaluate('() => window.__labShareState()')
    before = read()
    layers = before['layers']
    if len(layers) != 1 or layers[0]['template'] != tile_origin+'/tile/{z}/{x}/{y}.png':
        raise ValueError('Undeclared native tile provider')
    urls = []
    for tile in layers[0]['tiles']:
        a,b,c,d = tile['rect']
        if not tile['current'] or c <= a or d <= b: continue
        u = urlsplit(tile['src'])
        if (u.scheme, u.netloc) != (urlsplit(tile_origin).scheme, urlsplit(tile_origin).netloc) or u.query or u.fragment:
            raise ValueError('Tile outside this private service')
        tile_path(u.path)
        urls.append(tile['src'])
    records = warm_tiles(tile_origin, [urlsplit(u).path for u in urls], report, seconds=seconds)
    retried = page.locator('img.leaflet-tile').evaluate_all('''(es, urls) => {
      let n=0; for (const e of es) if (urls.includes(e.src) && e.complete && e.naturalWidth===0) {
        e.src=e.src; n++;
      } return n;
    }''', urls)
    page.wait_for_function('''urls => {
      const es=[...document.querySelectorAll('img.leaflet-tile')].filter(e=>urls.includes(e.src));
      return es.length>0 && es.every(e=>e.complete && e.naturalWidth===256 && e.naturalHeight===256);
    }''', arg=urls, timeout=15000)
    after = read()
    if any(before[k] != after[k] for k in ('zoom','center','bounds','size')):
        raise ValueError('Native view changed during tile readiness')
    return dict(tiles=len(records), retried_images=retried, geometry_unchanged=True)


def reopened_view(value, state, *, origin, expected_center, tile_origin):
    try: center=(state['zoom'],state['center']['lat'],state['center']['lng'])
    except (TypeError,KeyError): center=None
    return dict(explicit_view=view_link(value,origin=origin,expected_center=expected_center),
        original_native_center=center is not None and same_center(expected_center,center),
        rendered_standard=rendered_standard(state,tile_origin))


def embed_fitted_view(bbox,width,height):
    """Leaflet fitBounds for a Standard-layer iframe, independently calculated."""
    west,south,east,north=map(float,bbox)
    if (not all(math.isfinite(v) for v in (west,south,east,north)) or
        not -180<=west<east<=180 or not -85.05112878<south<north<85.05112878 or
        type(width) is not int or type(height) is not int or min(width,height)<=0):
        raise ValueError('Finite declared extent and positive iframe dimensions required')
    def y(lat):return (1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2
    left,right=(west+180)/360,(east+180)/360
    top,bottom=y(north),y(south)
    zoom=max(0,min(19,math.floor(math.log2(min(width/(256*(right-left)),height/(256*(bottom-top)))))))
    return zoom,math.degrees(math.atan(math.sinh(math.pi*(1-top-bottom)))),(left+right)*180-180


def reopened_embed(state, *, bbox,width,height,tile_origin):
    try:
        z,lat,lon=embed_fitted_view(bbox,width,height)
        actual=state['center'];world=256*2**z
        def p(y):return (1-math.asinh(math.tan(math.radians(y)))/math.pi)/2*world
        center_ok=(state['zoom']==z and abs((actual['lng']-lon)/360*world)<=1 and abs(p(actual['lat'])-p(lat))<=1)
        dimensions=state['size']==dict(width=width,height=height)
    except (ValueError,TypeError,KeyError,OverflowError): center_ok=dimensions=False
    return dict(original_extent_fit=center_ok,actual_dimensions=dimensions,rendered_standard=rendered_standard(state,tile_origin))
