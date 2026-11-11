"""Deterministic browser-location capability; not task admission on its own."""
import math
import re
from urllib.parse import parse_qs, urlsplit
from .map_view import read_map_view, native_zoom

# Public environment configuration, not coordinates inferred from actor actions.
# This is a local fixture; equivalence to an original recorded device is unknown.
FIXTURE={'latitude':40.7830,'longitude':-73.9650,'accuracy':25.0}
WRONG_FIXTURE={'latitude':40.7570,'longitude':-73.9860,'accuracy':25.0}


def validate_fixture(fixture):
    if not isinstance(fixture,dict) or set(fixture)!={'latitude','longitude','accuracy'}:
        raise ValueError('Complete browser geolocation fixture required')
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in fixture.values()):
        raise ValueError('Finite browser coordinates required')
    if not(-85<=fixture['latitude']<=85 and -180<=fixture['longitude']<=180 and 0<fixture['accuracy']<=1000):
        raise ValueError('Unsupported browser location or accuracy')


def read_geolocation_page(page):
    state=page.evaluate(r'''() => {
      const e=document.querySelector('.control-locate');
      const visible=n=>!!n&&!!n.getClientRects().length&&getComputedStyle(n).visibility!=='hidden';
      return {control_visible:visible(e),control_classes:e?[...e.classList]:[],
        links:e?[...e.querySelectorAll('a')].map(a=>({title:a.title,role:a.getAttribute('role')})):[]};
    }''')
    state['view']=read_map_view(page)
    return state


def settle_geolocation_page(page, site, evidence_path):
    """Wait for a request already initiated by the actor; never initiate it."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from .map_tile_warmup import warm_current_view
    try:
        page.wait_for_function("""() => {
          const e=document.querySelector('.control-locate');
          return !e || (!e.classList.contains('requesting') &&
            !document.querySelector('.leaflet-zoom-anim,.leaflet-pan-anim'));
        }""", timeout=20000)
    except PlaywrightTimeout:
        return read_geolocation_page(page)
    state = read_geolocation_page(page)
    if state['view'].get('map_visible') and 'active' in state['control_classes']:
        warm_current_view(page, site, evidence_path)
        state = read_geolocation_page(page)
    return state


def geolocation_checks(fixture,state):
    validate_fixture(fixture)
    if (not isinstance(state,dict) or type(state.get('control_visible'))is not bool
            or not isinstance(state.get('control_classes'),list)):
        raise ValueError('Missing native location-control capture')
    classes=state['control_classes'];view=state.get('view',{})
    checks={'native_location_active':state['control_visible'] and 'active'in classes and 'requesting'not in classes,
            'map_center_matches_location':False,'native_map_rendered':bool(view.get('map_visible') and view.get('tiles'))}
    try:
        zoom=native_zoom(view)
        geo=re.fullmatch(r'geo:([-\d.]+),([-\d.]+)\?z=(\d+)',view['native_geo_uri'])
        values=parse_qs(urlsplit(view['native_long_link']).fragment)['map']
        if len(values)!=1 or geo is None:return checks
        z,lat,lon=values[0].split('/')
        if int(z)!=zoom:return checks
        if zoom<1:return checks
        tolerance=0.5*10**(-math.ceil(math.log2(zoom)))+1e-7
        pairs=[(geo[1],geo[2]),(lat,lon)]
        checks['map_center_matches_location']=all(
            abs(float(v)-fixture[k])<=tolerance
            for pair in pairs for v,k in zip(pair,('latitude','longitude')))
    except (ValueError,KeyError,TypeError,AttributeError):pass
    return checks
