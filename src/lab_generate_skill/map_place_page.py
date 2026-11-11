"""Native place lookup/navigation, with private pinned identity references."""
import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit,urlencode
from .map_place_identity import identity,bounds,public_result_matches,native_view_in_place
from .map_view import read_map_view


def object_reference(xml,kind,number):
    if kind not in ('node','way','relation') or type(number)is not int or number<=0:raise ValueError('Invalid OSM identity')
    root=ET.fromstring(xml);objects=root.findall(kind)
    if len(objects)!=1 or objects[0].get('id')!=str(number):raise ValueError('Native object response has wrong identity')
    obj=objects[0]
    tags=sorted((t.get('k'),t.get('v')) for t in obj.findall('tag'))
    if any(not isinstance(k,str)or not isinstance(v,str)for k,v in tags):raise ValueError('Invalid native tags')
    return {'type':kind,'id':number,'version':obj.get('version'),'visible':obj.get('visible','true'),
            'tags':[list(t)for t in tags]}


def verify_reference(site,spec):
    ref=spec['reference'];kind,number=identity(ref);bounds(ref)
    with urllib.request.urlopen(site.search_url+'/search?'+urlencode({'q':spec['reference_query'],'format':'jsonv2','limit':20}),timeout=30)as response:
        rows=json.load(response)
    if len([r for r in rows if r==ref])!=1:raise ValueError('Pinned geographic identity changed or disappeared')
    with urllib.request.urlopen(site.url+f'/api/0.6/{kind}/{number}',timeout=30)as response:
        actual=object_reference(response.read(),kind,number)
    if actual!=spec['object_reference']:raise ValueError('Native object data differs from the pinned snapshot')


READ=r'''() => {
 const visible=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const sidebar=document.querySelector('#sidebar_content');
 return {page_snapshot:{url:location.href,title:document.title,heading_texts:[...document.querySelectorAll('h1,h2,h3')].map(e=>e.innerText.trim()),page_text:document.body.innerText.slice(0,30000)},
   path:location.pathname,query:document.querySelector('input[name="query"]')?.value||'',
   loading:[...document.querySelectorAll('#sidebar_loader,#sidebar_content .loader')].some(visible),
   map_async_loading:!!(window.jQuery&&jQuery.active>0)||!!document.querySelector('.leaflet-zoom-anim,.leaflet-pan-anim'),
   results:[...document.querySelectorAll('li.search_results_entry a.set_position')].filter(visible).map(e=>({
     path:e.getAttribute('href'),text:e.innerText,attributes:Object.fromEntries([...e.attributes].filter(a=>a.name.startsWith('data-')).map(a=>[a.name,a.value]))})),
   headings:[...document.querySelectorAll('#sidebar_content h2')].filter(visible).map(e=>e.innerText),
   sections:[...document.querySelectorAll('#sidebar_content .browse-section')].filter(visible).map(e=>e.className),
   tags:[...document.querySelectorAll('#sidebar_content table.browse-tag-list tr')].filter(visible).map(e=>[...e.querySelectorAll('th,td')].map(x=>x.innerText)),
   links:[...document.querySelectorAll('#sidebar_content .secondary-actions a')].filter(visible).map(e=>({text:e.innerText,path:e.getAttribute('href')}))};
}'''


def read_place_page(page):
    """Observe public readiness, never navigate or consult the task target."""
    path=urlsplit(page.url).path
    observed=path=='/search' or bool(re.fullmatch(r'/(node|way|relation)/[1-9][0-9]*',path)) or path=='/'
    deadline=time.monotonic()+15
    previous=None;stable_since=None
    while True:
        state=page.evaluate(READ);view=read_map_view(page);state['view']=view
        signal=(view.get('native_geo_uri'),view.get('native_long_link'),bool(view.get('tiles')),state['loading'],state.get('map_async_loading',False),len(state['results']),len(state['tags']))
        now=time.monotonic()
        if signal!=previous:previous=signal;stable_since=now
        # No expectation is inferred for non-place pages or deliberately blank
        # control fixtures. An actual loader remains diagnostic evidence.
        content=state['results'] if path=='/search' else state['tags'] if path!='/' else True
        # A relation's HTML/tags can finish before the native XML geometry
        # request pans the map. Old initial tiles do not prove the new view is
        # ready. Observe pending native requests/animation, not expected targets.
        ready=bool(view.get('native_geo_uri')) and bool(view.get('tiles')) and not state['loading'] and not state.get('map_async_loading',False)
        if not observed or (ready and content and now-stable_since>=.5) or now>=deadline:
            state['readiness_timeout']=bool(observed and content and not ready)
            return state
        # No asynchronous work or content on a known wrong/blank page.
        if not content and not state['loading'] and not state.get('map_async_loading',False) and now-stable_since>=.5:
            state['readiness_timeout']=False;return state
        page.wait_for_timeout(100)


def place_checks(spec,state):
    if not isinstance(state,dict) or any(k not in state for k in ('path','results','tags','sections','links','loading','view')):
        raise ValueError('Missing native place state')
    if state['loading'] or (spec['kind']!='information' and (state.get('readiness_timeout') or state.get('map_async_loading'))):raise ValueError('Native place content/map was still loading')
    ref=spec['reference'];kind,number=identity(ref);path=state['path']
    selected=path==f'/{kind}/{number}'
    sections=any('browse-'+kind in s.split()for s in state['sections'])
    tags=sorted(state['tags'])==sorted(spec['rendered_tags']) and bool(state['tags'])
    link=any(r.get('path')==f'/api/0.6/{kind}/{number}'for r in state['links'])
    detail=selected and sections and tags and link
    result=path=='/search' and any(public_result_matches(ref,r)for r in state['results'])
    correct_view=native_view_in_place(ref,state['view'])
    if spec['kind']=='information':
        return {'requested_place_identity':selected,'native_place_details':detail}
    if spec['kind']not in ('search','locate'):raise ValueError('Unsupported place task kind')
    return {'requested_place_identity':bool(result or detail or (spec['kind']=='locate' and path=='/' and correct_view)),
            'requested_place_map':correct_view}


def settle_place_tiles(page,site,report,state):
    """Complete pending native rendering without changing the chosen place.

    Only public current-page state is consulted. Wrong places remain wrong;
    no evaluator reference, pan, zoom, navigation, or model action is used.
    """
    view=state.get('view',{})
    if (state.get('readiness_timeout') is not True or state.get('loading') or state.get('map_async_loading')
        or view.get('map_visible') is not True or view.get('tiles')):
        return state
    from .map_tile_warmup import warm_current_view
    from .io_utils import atomic_write_json
    record=warm_current_view(page,site,report)
    atomic_write_json(report.with_name(report.stem+'-result.json'),record)
    return read_place_page(page)


FEEDBACK={'requested_place_identity':'The displayed result or object identifies the requested geographic place.',
          'native_place_details':'The requested object has loaded its native details and attributes.',
          'requested_place_map':'The native map displays the requested geographic area.'}
