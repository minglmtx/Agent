"""Proposed generic local layer completion; original tasks stay unchanged.

A generic layer task can complete through any supported actual local overlay;
MapData is required only when the original goal names it. Opening a catalog,
choosing a remote provider, checked DOM alone, pending warning or400 data is
not completion. This schema is staged, not normal admission proof.
"""
from collections import Counter
from decimal import Decimal
import hashlib,json,math
from urllib.parse import parse_qs,urljoin,urlsplit
from . import map_native_request_bounds as artifact
from .map_local_surface_controls import health,label_rows,read_surface
from .map_typed_information_share import layer_code,local_url
from .map_native_bbox_batch import VERSION as UNION_VERSION

VERSION='map-original-local-layer-transition-v1'
NOTE_MARKERS_READ=r'''() => {
 const visible=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).display!=='none';
 return {native_note_marker_icons: {
   open:window.OSM?.OPEN_NOTE_MARKER||null,closed:window.OSM?.CLOSED_NOTE_MARKER||null},
   native_active_overlays:typeof window.__labNativeLayerState==='function'?window.__labNativeLayerState():null,
   native_note_markers:[...document.querySelectorAll('.leaflet-marker-pane img.leaflet-marker-icon')]
    .filter(visible).map(e=>({title:e.getAttribute('title')||'',src:e.src,
      loaded:e.complete&&e.naturalWidth>0}))};
}'''


def read_layer_surface(page):
    """Ordinary visible native markers and public icon configuration only.

    The optional passive reader exposes real layer membership only. No marker
    IDs, task answers or actions are supplied. Route markers stay separate.
    """
    return dict(read_surface(page),**page.evaluate(NOTE_MARKERS_READ))

LOCAL_OVERLAYS={'Map Notes':'N','Map Data':'D'}


def proposed_scope(goal):
    if not isinstance(goal,str)or not goal.strip():raise ValueError('Original task goal required')
    explicit='map data'in goal.casefold()
    return {'version':VERSION,'original_goal':goal,'kind':'native_map_data'if explicit else'generic_local_layer_transition',
        'allowed_local_overlay_labels':['Map Data']if explicit else list(LOCAL_OVERLAYS),
        'preserve_original_area':'current view'in goal.casefold(),'normal_admitted':False,
        'semantic_review_required':True,'no_private_positive_steps_in_public_goal':True}


def _request(record,origin,path):
    if not isinstance(record,dict)or record.get('method')!='GET'or record.get('resource_type')!='xhr'or type(record.get('http_status'))is not int or record['http_status']!=200:return None
    url=record.get('url');u=urlsplit(url or '')
    if not local_url(url,origin)or u.path!=path or u.fragment:return None
    q=parse_qs(u.query,keep_blank_values=True)
    if set(q)!={'bbox'}or len(q['bbox'])!=1:return None
    try:return artifact.bbox(q['bbox'][0].split(','))
    except(ValueError,TypeError):return None


def notes_response_checks(record,body,origin):
    bounds=_request(record,origin,'/api/0.6/notes.json')
    result={'actual_same_origin_native_notes_http200':bounds is not None,'native_notes_json_valid':False,'unchanged_native_notes_area_limit':False}
    if bounds is not None:
        w,s,e,n=map(float,bounds)
        result['unchanged_native_notes_area_limit']=(e-w)*(n-s)<=25
    try:
        if record.get('content_type','').split(';',1)[0].strip().lower()not in('application/json','application/geo+json')or not isinstance(body,bytes)or not 1<=len(body)<=32*1024*1024:return result
        value=json.loads(body)
        if not isinstance(value,dict)or value.get('type')!='FeatureCollection'or not isinstance(value.get('features'),list)or len(value['features'])>10000:return result
        seen=set()
        for f in value['features']:
            if not isinstance(f,dict)or f.get('type')!='Feature':return result
            geometry=f.get('geometry');properties=f.get('properties')
            if not isinstance(geometry,dict)or geometry.get('type')!='Point'or not isinstance(geometry.get('coordinates'),list)or len(geometry['coordinates'])!=2 or not isinstance(properties,dict):return result
            coords=geometry['coordinates']
            if any(type(v)not in(int,float)or not math.isfinite(v)for v in coords)or not -180<=coords[0]<=180 or not -90<=coords[1]<=90:return result
            ident=properties.get('id')
            if type(ident)is not int or ident<=0 or ident in seen or properties.get('status')not in('open','closed'):return result
            comments=properties.get('comments')
            if not isinstance(comments,list)or not comments or not isinstance(comments[0],dict)or not isinstance(comments[0].get('text'),str):return result
            seen.add(ident)
        result['native_notes_json_valid']=True
    except(ValueError,KeyError,TypeError,AttributeError):pass
    return result


def notes_renderer_checks(body,terminal,origin):
    """Verify the visible native marker projection of an actual Notes response.

    Empty native Notes is a valid empty overlay. It does not imply MapData
    features or an alternative cartographic base style were rendered.
    """
    try:
        icons=terminal['native_note_marker_icons'];rows=terminal['native_note_markers']
        if not isinstance(icons,dict)or set(icons)!={'open','closed'}or not isinstance(rows,list):return False
        urls={status:urljoin(origin+'/',value) for status,value in icons.items() if isinstance(value,str)}
        if set(urls)!={'open','closed'}or len(set(urls.values()))!=2 or any(not local_url(v,origin)for v in urls.values()):return False
        reverse={v:k for k,v in urls.items()}
        expected=Counter((f['properties']['status'],f['properties']['comments'][0]['text'])for f in json.loads(body)['features'])
        observed=Counter()
        for row in rows:
            if not isinstance(row,dict)or set(row)!={'title','src','loaded'}or not isinstance(row['title'],str)or not isinstance(row['src'],str)or type(row['loaded'])is not bool:return False
            if row['src']in reverse:
                if row['loaded']is not True:return False
                observed[(reverse[row['src']],row['title'])]+=1
        return observed==expected
    except(ValueError,KeyError,TypeError,AttributeError):return False


def _comparison_valid(comparison,body,*,native):
    expected={'serialized_original_bounds','node_ids','node_versions_geometry_tags_members','way_ids','way_versions_geometry_tags_members','relation_ids','relation_versions_geometry_tags_members'}
    return (isinstance(body,bytes)and isinstance(comparison,dict)and comparison.get('version')==UNION_VERSION
        and comparison.get('passed')is True and isinstance(comparison.get('checks'),dict)
        and set(comparison['checks'])==expected and all(v is True for v in comparison['checks'].values())
        and comparison.get('api_payload_constructed_expected_reference')is False
        and comparison.get('native_single_map_http200_claim')is native
        and comparison.get('payload_sha256')==hashlib.sha256(body).hexdigest())


def _paths_added(initial,after):
    fields=('d','stroke','fill','class_name')
    try:
        old=Counter(tuple(p[k]for k in fields)for p in initial['rendered_paths']);new=Counter(tuple(p[k]for k in fields)for p in after['rendered_paths'])
        # Native browse.js requests per-feature styles through FeatureGroup.setStyle.
        # The bundled leaflet-osm DataLayer has no nested-style override: future
        # children can retain Leaflet's native #3388ff default. Both native paths
        # are valid. Keep route #03f/highlight #ff0 separate; checked DOM and a
        # new path alone remain insufficient without complete response checks.
        native_colors = {'#000000', '#00ff00', '#ff0000', '#3388ff'}
        return sum(n for p,n in(new-old).items()
                   if p[0] and p[1].lower() in native_colors
                   and 'leaflet-interactive' in p[3].split()) > 0
    except(KeyError,TypeError,AttributeError):return False


def _area_point_in_bounds(point,bounds):
    try:
        lat,lon=point;w,s,e,n=map(Decimal,artifact.bbox(bounds))
        return w<=Decimal(str(lon))<=e and s<=Decimal(str(lat))<=n
    except(ValueError,TypeError):return False


def layer_transition_checks(scope,initial,terminal,origin,*,notes_record=None,notes_body=None,
                            data_transport=None,data_comparison=None,data_record=None,data_body=None,original_area_point=None,initial_route=None,terminal_route=None,require_native_membership=False):
    checks={'valid_local_native_map':health(terminal,origin),'actual_supported_local_layer_changed':False,
        'native_selected_control_and_layer_code_agree':False,'actual_local_response_valid':False,
        'native_ajax_and_warning_settled':terminal.get('async_loading')is False and terminal.get('data_warning')is False,
        'original_current_area_preserved':not scope.get('preserve_original_area',False),
        'original_requested_native_route_preserved':not scope.get('retain_original_native_route',False)}
    if require_native_membership:checks['actual_native_leaflet_overlay_active']=False
    if scope.get('retain_original_native_route')is True:
        fields=('origin','destination','engine','rows','route_visible')
        checks['original_requested_native_route_preserved']=(isinstance(initial_route,dict)and isinstance(terminal_route,dict)and initial_route.get('route_visible')is True and terminal_route.get('route_visible')is True and bool(initial_route.get('rows'))and all(initial_route.get(k)==terminal_route.get(k)for k in fields))
    if scope.get('version')!=VERSION or scope.get('kind')not in('generic_local_layer_transition','native_map_data'):
        raise ValueError('Reviewed generic native layer schema required')
    try:
        before={r['label']:r for r in label_rows(initial,'overlays')};after={r['label']:r for r in label_rows(terminal,'overlays')}
        code=layer_code(terminal.get('native_long_link',''))
        if not local_url(terminal.get('native_long_link'),origin):return checks
    except(ValueError,TypeError,AttributeError):return checks
    for label in scope['allowed_local_overlay_labels']:
        if label not in LOCAL_OVERLAYS:raise ValueError('Only supported actual local overlay protocols allowed')
        b,a=before.get(label),after.get(label)
        changed=b is not None and a is not None and b['checked']is False and a['checked']is True and a['disabled']is False
        if require_native_membership:
            membership=terminal.get('native_active_overlays')
            changed=changed and isinstance(membership,dict)and set(membership)==set(LOCAL_OVERLAYS)and all(type(v)is bool for v in membership.values())and membership[label]is True
        else:
            # Archived evidence lacks the passive getter; do not invent it.
            changed=changed and a is not None and a['visible']is True
        if not changed or LOCAL_OVERLAYS[label]not in code:continue
        response_ok=False;bounds=None
        if label=='Map Notes':
            values=notes_response_checks(notes_record,notes_body,origin)
            response_ok=all(v is True for v in values.values())and notes_renderer_checks(notes_body,terminal,origin);bounds=_request(notes_record,origin,'/api/0.6/notes.json')
            # Empty native Notes is an actual enabled empty overlay, not a
            # fabricated visual style or successful MapData render.
        else:
            coverage_fields={'all_cells_within_original','interiors_disjoint','exact_original_area_covered'}
            transport_ok=(isinstance(data_transport,dict)and data_transport.get('version')==UNION_VERSION
                and type(data_transport.get('native_parent_http_status'))is int and data_transport['native_parent_http_status']==400
                and data_transport.get('native_node_limit_changed')is False
                and data_transport.get('native_single_request_success')is False
                and isinstance(data_transport.get('coverage'),dict)and set(data_transport['coverage'])==coverage_fields
                and all(v is True for v in data_transport['coverage'].values())
                and data_transport.get('each_child_uses_original_native_endpoint')is True
                and isinstance(data_body,bytes)and data_transport.get('sha256')==hashlib.sha256(data_body).hexdigest())
            adapted_ok=transport_ok and _comparison_valid(data_comparison,data_body,native=False)
            native_bounds=_request(data_record,origin,'/api/0.6/map')
            direct_ok=(native_bounds is not None and isinstance(data_record.get('content_type'),str)
                and data_record['content_type'].split(';',1)[0].strip().lower()in('application/xml','text/xml')
                and _comparison_valid(data_comparison,data_body,native=True))
            response_ok=(adapted_ok or direct_ok)and _paths_added(initial,terminal)
            bounds=data_transport.get('bounds')if adapted_ok else native_bounds
        if response_ok:
            if require_native_membership:checks['actual_native_leaflet_overlay_active']=True
            checks.update(actual_supported_local_layer_changed=True,native_selected_control_and_layer_code_agree=True,actual_local_response_valid=True)
            if scope.get('preserve_original_area'):checks['original_current_area_preserved']=_area_point_in_bounds(original_area_point,bounds)
            break
    return checks
