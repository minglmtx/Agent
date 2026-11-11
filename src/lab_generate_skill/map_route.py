"""Native rendered directions checked against immutable local routing references."""
import math
import re
import urllib.parse
import urllib.request

LABELS={'car':'Car (OSRM)','bike':'Bicycle (OSRM)','foot':'Foot (OSRM)'}


def set_unsubmitted_route_control(page,pair):
    """Negative control only: edit the visible form without submitting a route."""
    for name,point in zip(('route_from','route_to'),pair):
        field=page.locator(f'input[name="{name}"]:visible')
        if field.count()!=1:raise ValueError('Expected one visible native route input: '+name)
        field.evaluate('(e,v)=>{e.value=v}',','.join(map(str,point)))


def route_path(pair,profile):
    if profile not in LABELS:raise ValueError('Unsupported route profile')
    return '/directions?'+urllib.parse.urlencode({'engine':'fossgis_osrm_'+profile,
        'route':';'.join(str(x)+','+str(y) for x,y in pair)})


def backend_reference(site,pair,profile):
    coords=';'.join(str(y)+','+str(x) for x,y in pair)
    with urllib.request.urlopen(site.route_urls[profile]+'/route/v1/driving/'+coords+'?overview=false&steps=true',timeout=30) as response:
        data=__import__('json').load(response)
    if data.get('code')!='Ok' or len(data.get('routes',[]))!=1:raise ValueError('Expected local route unavailable')
    return data['routes'][0]


def verify_route_reference(site,spec):
    for ref in spec['alternatives']:
        if backend_reference(site,spec['pair'],ref['profile'])!=ref['backend']:
            raise ValueError('Native routing snapshot differs from pinned reference')
    if spec.get('initial_route'):
        if spec['initial_route'].get('initial_route'):
            raise ValueError('Nested initial route is unsupported')
        verify_route_reference(site,spec['initial_route'])


def require_initial_route(spec,state,url):
    """Transformation precondition, checked before the first actor generation."""
    initial=spec.get('initial_route')
    if initial is None:return None
    if not all(route_checks(initial,state,url).values()):
        raise ValueError('Initial native route differs from the recorded task state')
    if all(route_checks(spec,state,url).values()):
        raise ValueError('Route transformation target is already satisfied initially')
    return True


def observe_initial_route(page,spec):
    """Wait only for an explicit initial directions request, without performing actions."""
    if spec.get('initial_route') is None:return None
    url=urllib.parse.urlsplit(page.url)
    params=urllib.parse.parse_qs(url.query)
    if url.path.rstrip('/')!='/directions' or len(params.get('route',[]))!=1:
        raise ValueError('Original directions initialization did not reach its route page')
    page.wait_for_function("() => !!document.querySelector('#sidebar_content tr.turn') || !!document.querySelector('#sidebar_content .search_results_error')",timeout=30000)
    from .browser_page_wait import READY,probe_args
    page.wait_for_function(READY,arg=probe_args('map'),timeout=8000,polling=100)
    state=read_route(page)
    require_initial_route(spec,state,page.url)
    return state


def read_route(page):
    return page.evaluate(r'''() => {
      const visible=e=>!!e && !!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
      const field=selector=>{
        const matches=[...document.querySelectorAll(selector)].filter(visible);
        if(matches.length>1) throw new Error('Ambiguous visible native route control: '+selector);
        return matches[0];
      };
      const sidebar=document.querySelector('#sidebar_content');
      return {origin:field('input[name="route_from"]')?.value || '',
        destination:field('input[name="route_to"]')?.value || '',
        engine:field('select.routing_engines')?.selectedOptions[0]?.text || '',
        route_form_visible:!!(field('input[name="route_from"]') || field('input[name="route_to"]') || field('select.routing_engines')),
        summary:sidebar?.innerText || '',
        rows:[...document.querySelectorAll('#sidebar_content tr.turn')].map(e=>e.innerText),
        route_visible:[...document.querySelectorAll('.leaflet-overlay-pane path[stroke="#03f"]')].some(e=>visible(e) && (e.getAttribute('d')||'').length>20),
        loading:[...document.querySelectorAll('#sidebar_loader,#sidebar_content .loader')].some(visible)};
    }''')


def normalized(s):return re.sub(r'\s+',' ',s).strip()


def parse_point(text):
    try:
        values=[float(x.strip()) for x in text.split(',')]
        if len(values)!=2 or not all(math.isfinite(x) for x in values):return None
        return values
    except (ValueError,TypeError,AttributeError):return None


def pair_equal(a,b):
    return len(a)==len(b)==2 and all(x is not None and y is not None and len(x)==len(y)==2 and
        all(abs(v-w)<1e-8 for v,w in zip(x,y)) for x,y in zip(a,b))


def native_rounded_point(text,point):
    """OSM directions.js writes toFixed(zoomPrecision) coordinates to the URL.

    This is only used with named-place identity AND exact native route content;
    it must never serve as a standalone place or route success check.
    """
    if not isinstance(text,str) or len(point)!=2:return False
    pieces=text.split(',')
    if len(pieces)!=2:return False
    for token,value in zip(pieces,point):
        m=re.fullmatch(r'\s*[+-]?\d+(?:\.(\d{1,8}))?\s*',token)
        if not m:return False
        digits=len(m.group(1) or '')
        if abs(float(token)-value)>0.5*10**(-digits)+1e-10:return False
    return True


def capability_signature(record):
    """Compare native route semantics, allowing only verified URL rounding.

    Leaflet's current zoom controls URL precision. Exact backend endpoints,
    route response, form labels and rendered directions must still match.
    """
    u=urllib.parse.urlsplit(record['path']);params=urllib.parse.parse_qs(u.query)
    profile=record['profile'];pair=record['pair']
    points=params.get('route',[''])[0].split(';')
    if (record.get('error') or u.path!='/directions' or set(params)!={'engine','route'}
        or params['engine']!=['fossgis_osrm_'+profile] or len(params['route'])!=1
        or len(points)!=2 or not pair or len(pair)!=2
        or not all(native_rounded_point(s,p) for s,p in zip(points,pair))):
        raise ValueError('Native route URL does not identify its exact backend route')
    return {k:record[k] for k in ('origin','destination','profile','native','pair','backend','native_backend_request_path')}


def route_checks(spec,state,url):
    required={'origin','destination','engine','summary','rows','route_visible','loading'}
    if not isinstance(state,dict) or not required<=state.keys():raise ValueError('Missing native route capture')
    if state['loading']:raise ValueError('Native route was still loading at termination')
    if not isinstance(state['rows'],list) or any(not isinstance(x,str) for x in state['rows']):raise ValueError('Malformed route rows')
    params=urllib.parse.parse_qs(urllib.parse.urlsplit(url).query,keep_blank_values=True)
    declared=params.get('route',[]);engines=params.get('engine',[])
    pair=[parse_point(x) for x in declared[0].split(';')] if len(declared)==1 else []
    form_absent=state.get('route_form_visible') is False and all(state[k]=='' for k in ('origin','destination','engine'))
    choices=[r for r in spec['alternatives'] if engines==['fossgis_osrm_'+r['profile']] and (state['engine']==LABELS[r['profile']] or form_absent)]
    same=lambda ref:normalized(state['summary'])==normalized(ref['native']['summary']) and [normalized(x) for x in state['rows']]==[normalized(x) for x in ref['native']['rows']]
    endpoints=pair_equal(pair,spec['pair']) and pair_equal([parse_point(state['origin']),parse_point(state['destination'])],spec['pair'])
    if spec.get('endpoint_labels'):
        labels=spec['endpoint_labels']
        if len(labels)!=2 or any(not isinstance(x,list) or not x or any(not isinstance(y,str) or not y for y in x) for x in labels):raise ValueError('Missing named-place identity references')
        raw=declared[0].split(';') if len(declared)==1 else []
        url_ok=len(raw)==2 and all(native_rounded_point(x,p) for x,p in zip(raw,spec['pair']))
        fields=[state['origin'],state['destination']]
        names_ok=all(normalized(x).casefold() in {normalized(y).casefold() for y in names} or native_rounded_point(x,p)
                     for x,names,p in zip(fields,labels,spec['pair']))
        endpoints=url_ok and names_ok
    if form_absent:
        # Native asynchronous route completion can leave its input form hidden
        # after a sidebar transition. URL alone is insufficient: require the
        # entire rendered reference and visible route as independent evidence.
        url_endpoints=url_ok if spec.get('endpoint_labels') else pair_equal(pair,spec['pair'])
        endpoints=url_endpoints and len(choices)==1 and bool(state['rows']) and same(choices[0]) and state['route_visible'] is True
    return {'route_endpoints':endpoints,
            'route_transport_mode':len(choices)==1,
            'route_rendered_content':len(choices)==1 and bool(state['rows']) and same(choices[0]),
            'route_line_displayed':state['route_visible'] is True}


FEEDBACK={'route_endpoints':'The displayed directions use the requested starting and destination locations in the requested order.',
          'route_transport_mode':'The displayed directions use a transportation mode allowed by the task.',
          'route_rendered_content':'The actual directions, distance and time match the displayed route and mode.',
          'route_line_displayed':'The computed route is displayed on the native map.'}
