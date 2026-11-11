"""Read native map view state without trusting editable share/URL inputs.

The pinned OSM frontend updates #geo_uri and #long_link from its map object
on moveend. Reading these links adds no action and exposes no private answer
to the actor. The editable #long_input is retained only as diagnostic evidence.
"""
import math
import re
import time
from urllib.parse import urlsplit, parse_qs

READ = r'''() => {
 const visible=e=>!!e && !!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
 return {path:location.pathname+location.search+location.hash,
   map_visible:visible(document.querySelector('#map')),
   native_share_url:document.querySelector('#long_input')?.value||'',
   native_long_link:document.querySelector('#long_link')?.getAttribute('href')||'',
   native_geo_uri:document.querySelector('#geo_uri')?.getAttribute('href')||'',
   scale:[...document.querySelectorAll('.leaflet-control-scale-line')].filter(visible).map(e=>e.innerText),
   tiles:[...document.querySelectorAll('img.leaflet-tile')].filter(e=>visible(e)&&e.complete&&e.naturalWidth>0).map(e=>({path:new URL(e.src).pathname,width:e.naturalWidth,parent_style:e.parentElement.getAttribute('style')})),
   zoom_controls:[...document.querySelectorAll('.zoom a.control-button')].filter(visible).map(e=>({title:e.title,text:e.innerText,disabled:e.classList.contains('disabled')}))};
}'''


def read_map_view(page):
    return page.evaluate(READ)


READINESS = r'''args => {
 const visible=e=>!!e && !!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
 const map=document.querySelector('#map');
 const geo=document.querySelector('#geo_uri')?.getAttribute('href')||'';
 const long=document.querySelector('#long_link')?.getAttribute('href')||'';
 const match=geo.match(/^geo:([-+]?\d+(?:\.\d+)?),([-+]?\d+(?:\.\d+)?)\?z=(\d+)$/);
 let parts=null;
 try {
   const values=new URLSearchParams(new URL(long,location.href).hash.slice(1)).getAll('map');
   if(values.length===1 && /^\d+\/[-+]?\d+(?:\.\d+)?\/[-+]?\d+(?:\.\d+)?$/.test(values[0])) {
     parts=values[0].split('/').map(Number);
   }
 } catch(error) {}
 const longitudeDistance=(a,b)=>Math.abs(((a-b+180)%360+360)%360-180);
 const busy=!!document.querySelector('.leaflet-zoom-anim,.leaflet-pan-anim') ||
   ((args.search || args.directions) && !!(window.jQuery && jQuery.active>0));
 const loading=(args.search || args.directions) &&
   [...document.querySelectorAll('#sidebar_loader,#sidebar_content .loader')].some(visible);
 let ready=visible(map)&&!!match&&!!parts&&!!document.querySelector('#long_input')?.value&&!busy;
 if(ready) {
   const lat=Number(match[1]),lon=Number(match[2]),zoom=Number(match[3]);
   ready=Number.isFinite(lat)&&Number.isFinite(lon)&&lat>=-90&&lat<=90&&lon>=-180&&lon<=180&&
     zoom>=0&&zoom<=30&&parts.every(Number.isFinite)&&parts[1]>=-90&&parts[1]<=90&&
     parts[2]>=-180&&parts[2]<=180&&parts[0]===zoom&&Math.abs(parts[1]-lat)<=1e-9&&longitudeDistance(parts[2],lon)<=1e-9;
   if(args.expectedZoom!==null) ready=ready&&zoom===args.expectedZoom;
   if(args.expectedCenter!==null) ready=ready&&
     Math.abs(lat-args.expectedCenter.lat)<=args.centerTolerance&&
     longitudeDistance(lon,args.expectedCenter.lon)<=args.centerTolerance;
 }
 if(args.search) {
   const entries=[...document.querySelectorAll('#sidebar_content .search_results_entry[data-href]')];
   ready=ready&&entries.length>0&&entries.every(e=>e.textContent.trim())&&!loading;
 }
 let directionsContent=null;
 const directionsFields=args.directions ? ['input[name=route_from]','input[name=route_to]','select.routing_engines'].map(
   selector=>({selector,total:document.querySelectorAll(selector).length,
     visible:[...document.querySelectorAll(selector)].filter(visible).length})) : null;
 if(args.directions) {
   if(args.routeRequest) {
     // Observe the native request's outcome, not its expected route or target.
     directionsContent=!!document.querySelector('#sidebar_content tr.turn') ||
       [...document.querySelectorAll('#sidebar_content .search_results_error')].some(visible);
   } else {
     directionsContent=directionsFields.every(field=>field.visible===1);
   }
   ready=ready&&directionsContent&&!loading;
 }
 return {geo,long,classes:map?.className||'',busy,loading,directionsContent,directionsFields,ready:!!ready};
}'''


def wait_native_view(page, initial_path, *, timeout=45000):
    """Wait for native map initialization without changing the requested view.

    Plain '/' fragment navigation must reach its requested center, not merely
    the same zoom as the previous view. Native links must agree and settle;
    editable share inputs are not used as proof of coordinates. Search and
    directions retain native auto-pan semantics rather than a literal-center
    requirement. No task target or execution strategy is supplied to the page.
    """
    deadline=time.monotonic()+timeout/1000
    requested=urlsplit(initial_path)
    if requested.scheme or requested.netloc or requested.path not in ('/', '/search', '/directions'):
        raise ValueError('Explicit local map start required')
    plain=requested.path=='/'
    # Native search/directions URLs can acquire their map fragment only after
    # asynchronous auto-pan. They still need matching, settled native signals
    # below; a supplied fragment must remain valid, even on those pages.
    zoom=lat=lon=None
    if plain or requested.fragment:
        values=parse_qs(requested.fragment).get('map', [])
        if len(values)!=1 or not re.fullmatch(r'\d+/[-+]?\d+(?:\.\d+)?/[-+]?\d+(?:\.\d+)?',values[0]):
            raise ValueError('Explicit initial map view required')
        zoom_text,lat_text,lon_text=values[0].split('/')
        zoom,lat,lon=int(zoom_text),float(lat_text),float(lon_text)
        if not (0<=zoom<=30 and math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180):
            raise ValueError('Requested native map view is outside geographic bounds')
    args={'search':requested.path=='/search','expectedZoom':zoom if plain else None,
          'expectedCenter':{'lat':lat,'lon':lon} if plain else None,
          'centerTolerance':0.5*10**-max(0,math.ceil(math.log2(max(zoom or 1,1))))+1e-9,
          'directions':requested.path=='/directions',
          'routeRequest':bool(parse_qs(requested.query,keep_blank_values=True).get('route'))}
    from playwright.sync_api import TimeoutError as BrowserTimeout
    def timeout_evidence(error):
        # Ordinary map links only; never read an OAuth/editor DOM or hash.
        error.last_native_view=None
        error.last_native_readiness=None
        try:
            error.last_native_view=read_map_view(page)
            error.last_native_readiness=page.evaluate(READINESS,args)
        except Exception:
            # A closed browser must not replace the original timeout evidence.
            pass
        return error
    try:
        page.wait_for_function('args => ('+READINESS+')(args).ready',arg=args,
            timeout=max(1,(deadline-time.monotonic())*1000))
    except BrowserTimeout as exc:
        raise timeout_evidence(exc)
    # AJAX completion/hashchange can precede native moveend/share publication.
    # Directions retain auto-pan: observe content/animation and settled native
    # links, without comparing to a requested route or literal original center.
    previous=None;stable_since=None
    while time.monotonic()<deadline:
        signal=page.evaluate(READINESS,args)
        now=time.monotonic()
        if signal!=previous or not signal['ready']:
            previous=signal;stable_since=now
        elif stable_since is not None and now-stable_since>=.75:
            state=read_map_view(page);native_zoom(state);return state
        page.wait_for_timeout(min(100,max(1,(deadline-time.monotonic())*1000)))
    raise timeout_evidence(BrowserTimeout('Native map did not settle within its readiness budget'))


def native_zoom(state):
    """Require agreement of two native map-derived, non-editable signals."""
    if not isinstance(state, dict) or type(state.get('map_visible')) is not bool:
        raise ValueError('Missing native map view capture')
    uri = state.get('native_geo_uri')
    if not isinstance(uri, str):
        raise ValueError('Missing native map Geo URI')
    match = re.fullmatch(r'geo:([-+]?\d+(?:\.\d+)?),([-+]?\d+(?:\.\d+)?)\?z=(\d+)', uri)
    if not match:
        raise ValueError('Malformed native map Geo URI')
    lat, lon = map(float, match.groups()[:2])
    zoom = int(match[3])
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180 and 0 <= zoom <= 30):
        raise ValueError('Native map view is outside geographic bounds')
    link = state.get('native_long_link')
    if not isinstance(link, str):
        raise ValueError('Missing native map link')
    values = parse_qs(urlsplit(link).fragment).get('map', [])
    if len(values) != 1:
        raise ValueError('Ambiguous native map link')
    parts = values[0].split('/')
    if len(parts) != 3 or not parts[0].isdigit() or int(parts[0]) != zoom:
        raise ValueError('Native map signals disagree on zoom')
    return zoom


def zoom_checks(direction, initial, final):
    """Terminal zoom change only; this is not a geographic/search evaluator."""
    if direction not in ('in', 'out', 'change'):
        raise ValueError('Unsupported zoom direction')
    old, new = native_zoom(initial), native_zoom(final)
    if not isinstance(final.get('tiles'), list):
        raise ValueError('Missing map rendering evidence')
    return {'map_view_present': final['map_visible'],
            'map_tiles_present': bool(final['tiles']),
            'requested_zoom_change': new > old if direction == 'in' else new < old if direction == 'out' else new != old}
