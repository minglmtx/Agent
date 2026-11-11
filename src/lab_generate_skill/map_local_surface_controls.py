"""Generic public native Map surface checks; private controls, never task admission.

Readers inspect ordinary DOM and exact locally observed response bytes. No
hidden task answers, account form values, provider substitutions or JS actions
are exposed to an actor. Capability and original semantic completion are separate.
"""
import hashlib
import json
import math
from collections import Counter
from urllib.parse import parse_qs, urlsplit
from .map_frontier_capabilities import native_view, native_displaced, relative_zoom
from .map_local_capabilities import same_center, map_triplet
from .map_share_layout import resized_center
from .map_typed_information_share import local_url, layer_code
from .map_osm_native_reference import VERSION as NATIVE_REFERENCE_VERSION

VERSION='map-public-local-surface-controls-v1'

READ=r'''() => {
 const visible=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).display!=='none';
 const labels=scope=>[...document.querySelectorAll(scope+' label')].map(e=>{
  const input=e.querySelector('input');return {label:e.textContent.trim(),visible:visible(e),
    checked:input?input.checked:null,disabled:input?input.disabled:null,type:input?input.type:null};});
 const paths=[...document.querySelectorAll('.leaflet-overlay-pane svg path')].filter(visible).map(e=>({
  d:e.getAttribute('d')||'',stroke:e.getAttribute('stroke')||'',fill:e.getAttribute('fill')||'',
  class_name:e.getAttribute('class')||''}));
 return {url:location.href,map_visible:visible(document.querySelector('#map')),
  layers_visible:visible(document.querySelector('.layers-ui')),
  base:labels('.base-layers'),overlays:labels('.overlay-layers'),rendered_paths:paths,
  native_geo_uri:document.querySelector('#geo_uri')?.getAttribute('href')||null,
  native_long_link:document.querySelector('#long_link')?.getAttribute('href')||null,
  data_warning:visible(document.querySelector('#browse_status input[type=submit]')),
  async_loading:!!(window.jQuery&&jQuery.active>0),
  thunderforest_enabled:!!(window.OSM&&OSM.THUNDERFOREST_KEY),
  headings:[...document.querySelectorAll('h1,h2,h3,h4')].filter(visible).map(e=>e.innerText.trim())};
}'''

REGISTRATION_READ=r'''() => {
 const visible=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).display!=='none';
 const fs=[...document.querySelectorAll('form')].filter(visible).map(f=>({
  path:new URL(f.action,location.href).pathname,local:new URL(f.action,location.href).origin===location.origin,
  method:f.method.toLowerCase(),
  fields:[...f.querySelectorAll('input,select,textarea')].filter(e=>visible(e)&&e.type!=='hidden').map(e=>({name:e.name,type:e.type,id:e.id,required:e.required})),
  submits:[...f.querySelectorAll('button,input[type=submit]')].filter(visible).map(e=>(e.innerText||e.value||'').trim())}));
 return {url:location.href,anonymous_header:visible(document.querySelector('header .login-menu')),
  authenticated_header:visible(document.querySelector('header .user-menu.logged-in')),
  forms:fs,headings:[...document.querySelectorAll('h1,h2,h3')].filter(visible).map(e=>e.innerText.trim()),
  public_links:[...document.querySelectorAll('a[href]')].filter(visible).map(e=>({text:e.innerText.trim(),
    path:new URL(e.href).pathname,local:new URL(e.href).origin===location.origin})),form_values_captured:false};
}'''


def read_surface(page):return page.evaluate(READ)
def read_registration(page):return page.evaluate(REGISTRATION_READ)
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def health(state,origin):
    if not isinstance(state,dict)or not isinstance(state.get('url'),str):return False
    p=urlsplit(state['url'])
    return local_url(state['url'],origin)and p.path not in ('/login','/user/new')and not p.path.startswith('/__')and state.get('map_visible')is True


def label_rows(state,key):
    rows=state.get(key)
    if not isinstance(rows,list):raise ValueError('Public native control catalog missing')
    labels=[]
    for r in rows:
        if not isinstance(r,dict)or not isinstance(r.get('label'),str)or not r['label']or any(type(r.get(k))is not bool for k in ('visible','checked','disabled'))or r.get('type')not in ('radio','checkbox'):
            raise ValueError('Public native control datatype changed')
        labels.append(r['label'])
    if len(set(labels))!=len(labels):raise ValueError('Public native labels ambiguous')
    return rows


def catalog_checks(state,origin,expected):
    base=label_rows(state,'base');overlays=label_rows(state,'overlays')
    return {'valid_local_map':health(state,origin),'visible_layer_catalog':state.get('layers_visible')is True,
            'complete_native_base_labels':[r['label']for r in base]==expected['base'],
            'complete_native_overlay_labels':[r['label']for r in overlays]==expected['overlays'],
            'all_catalog_controls_visible':all(r['visible']for r in base+overlays),
            'native_selected_base_unique':sum(r['checked']for r in base)==1}


def data_overlay_checks(state,origin,reference,*,api_comparison=None,initial_paths=()):
    overlays=label_rows(state,'overlays')
    rows=[r for r in overlays if r['label']=='Map Data']
    paths=state.get('rendered_paths')
    if not isinstance(paths,list)or any(not isinstance(p,dict)or set(p)!={'d','stroke','fill','class_name'}or any(not isinstance(v,str)for v in p.values())for p in paths):
        raise ValueError('Public native path capture datatype changed')
    observed=Counter(tuple(p[k]for k in ('d','stroke','fill','class_name'))for p in paths)
    before=Counter(tuple(p[k]for k in ('d','stroke','fill','class_name'))for p in initial_paths)
    added=observed-before
    # These are installed native DataLayer styles, distinct from the blue
    # route polyline. Real API/DB equality alone is not rendered UI completion.
    native_added=sum(n for p,n in added.items()if p[1].lower()in ('#000000','#00ff00','#ff0000')and p[0])
    api_fields={'node_ids','node_content','way_ids','way_content','relation_ids','relation_content','native_bounds'}
    api_ok=(isinstance(api_comparison,dict)and api_comparison.get('version')==NATIVE_REFERENCE_VERSION and api_comparison.get('passed')is True and
        isinstance(api_comparison.get('checks'),dict)and set(api_comparison['checks'])==api_fields and all(v is True for v in api_comparison['checks'].values()))
    return {'valid_local_map':health(state,origin),'native_map_data_checked':len(rows)==1 and rows[0]['visible']and rows[0]['checked']and not rows[0]['disabled'],
        'same_reference_current_view':state.get('native_geo_uri')==reference.get('native_geo_uri'),
        'actual_native_full_api_database_objects_equal':api_ok,
        'native_data_paths_rendered':native_added>0,
        'no_unresolved_data_warning':state.get('data_warning')is False,
        'native_ajax_settled':state.get('async_loading')is False}


def registration_checks(state,origin):
    forms=state.get('forms')if isinstance(state,dict)else None
    if not isinstance(forms,list)or any(not isinstance(f,dict)or not isinstance(f.get('fields'),list)or not isinstance(f.get('submits'),list)or any(not isinstance(v,str)for v in f['submits'])for f in forms):raise ValueError('Native registration forms missing or malformed')
    p=urlsplit(state.get('url',''))
    rows=[f for f in forms if f.get('local')is True and f.get('path')=='/user/new'and f.get('method')=='post']
    fields=rows[0].get('fields',[])if len(rows)==1 else []
    if any(not isinstance(r,dict)or not isinstance(r.get('name'),str)or not isinstance(r.get('type'),str)or type(r.get('required'))is not bool for r in fields):
        raise ValueError('Native registration field datatype changed')
    wanted={'user[email]':'email','user[email_confirmation]':'email','user[display_name]':'text',
            'user[pass_crypt]':'password','user[pass_crypt_confirmation]':'password'}
    return {'same_origin':local_url(state.get('url'),origin),'native_registration_path':p.path=='/user/new',
      'anonymous_unpreauthenticated':state.get('anonymous_header')is True and state.get('authenticated_header')is False,
      'native_registration_post_form':len(rows)==1,
      'all_required_original_account_fields':all(sum(f.get('name')==k and f.get('type')==v for f in fields)==1 for k,v in wanted.items()),
      'native_continue_control':len(rows)==1 and bool(rows[0].get('submits')),
      'no_form_values_or_tokens_saved':state.get('form_values_captured')is False}


def share_checks(state,origin,initial,geometry):
    if not isinstance(state,dict):raise ValueError('Native public Share state missing')
    expected=resized_center(*native_view(initial),geometry)
    checks={'native_share_visible':state.get('visible')is True,'native_map_visible':state.get('map_visible')is True,
            'original_native_standard_layer':state.get('active_base_labels')==state.get('checked_base_labels')==['Standard']and state.get('active_overlay_labels')==[]}
    for k in ('long','short'):
        value=state.get(k+'_href');valid=local_url(value,origin)
        if valid:
            from .map_share_query import short_path
            p=urlsplit(value)
            valid=(p.path=='/'and not p.query and same_center(expected,map_triplet(value)))if k=='long'else(p.path==short_path(*expected)and not p.query and not p.fragment)
            valid=valid and layer_code(value)=='M'
        checks['native_'+k+'_geometry']=bool(valid)
        tabs=state.get('tab_captures',{})
        tab=tabs.get(k)if isinstance(tabs,dict)else None
        checks['native_'+k+'_visible_value']=(isinstance(tab,dict)and tab.get('visible')is True and tab.get('value')==value and tab.get('href')==value)
    return checks


def two_fresh_sources(cycles,sources):
    if len(cycles)!=2 or len(set(sources))!=len(sources):return []
    if not cycles[0].get('initial_fingerprint')or cycles[0]['initial_fingerprint']!=cycles[1].get('initial_fingerprint'):return []
    if any(c.get('protected_state_unchanged')is not True or c.get('clean_reset_verified')is not True or c.get('dirty_reuse_refused')is not True for c in cycles):return []
    complete=[]
    for tid in sources:
        pair=[[r for r in c.get('sources',[])if r.get('source_task_id')==tid]for c in cycles]
        if any(len(r)!=1 for r in pair):continue
        a,b=pair[0][0],pair[1][0]
        if a.get('capability_checks_passed')is True and b.get('capability_checks_passed')is True and a.get('reference_signature')and a['reference_signature']==b.get('reference_signature'):
            complete.append(tid)
    return complete


def relative_checks(kind,state,origin,initial):
    if kind not in ('pan','zoom_in'):raise ValueError('Unknown native relative-view kind')
    good=health(state,origin)
    try:
        change=native_displaced(initial,state)if kind=='pan'else relative_zoom(initial,state)
    except ValueError:
        change=False
    return {'valid_local_map':good,'native_relative_change':change,
      'actual_local_tiles_rendered':bool(state.get('tiles'))and all(isinstance(t,dict)and t.get('width',0)>0 for t in state['tiles'])}


def reverse_checks(state,origin,initial):
    if not isinstance(state,dict):raise ValueError('Native reverse capture missing')
    rows=state.get('reverse_results')
    if not isinstance(rows,list)or any(not isinstance(r,dict)or set(r)!={'text','path','lat','lon','type','id'}or any(not isinstance(v,str)for v in r.values())for r in rows):raise ValueError('Complete native reverse result datatype changed')
    identity_ok=bool(rows)and all(r['text'].strip()and r['type']in ('node','way','relation')and r['id'].isdigit()and int(r['id'])>0 and r['path']=='/'+r['type']+'/'+r['id']for r in rows)
    z,lat,lon=native_view(initial);q=parse_qs(urlsplit(state.get('url','')).query,keep_blank_values=True)
    query=q.get('query',[])
    try:point=[float(v.strip())for v in query[0].split(',')]if len(query)==1 else []
    except ValueError:point=[]
    return {'same_origin':local_url(state.get('url'),origin),'native_reverse_page':urlsplit(state.get('url','')).path=='/search'and q.get('whereami')==['1'],
      'original_native_center_query':len(point)==2 and math.isclose(point[0],lat,abs_tol=1e-7)and math.isclose(point[1],lon,abs_tol=1e-7),
      'visible_complete_reverse_result':state.get('reverse_visible')is True and identity_ok and state.get('loading')is False,
      'actual_trusted_whereami_activation':state.get('trusted_activation')is True}
