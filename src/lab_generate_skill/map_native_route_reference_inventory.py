"""Capture full native reference candidates once per factory; no task admission.

This runs inside an already cold-started normal Map factory. No external
geocoder/router is accepted and source goals are never used to guess an
arbitrary initial pair. Returned full geocoder records remain candidates until
semantic identity selection is independently declared and normal controls pass.
"""
from copy import deepcopy
from decimal import Decimal
import hashlib,json,time
from pathlib import Path
from urllib.parse import urlencode,urlsplit
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from .map_route_normal_capture import complete_route,point,fingerprint


def original_queries(request):
    kind=request['kind']
    if kind=='named_places':return list(request['queries'])
    if kind=='reverse_named_initial_route':return list(request['initial_queries'])
    if kind in ('one_native_field','replace_one_endpoint'):
        return [request['query']] if request.get('query') else []
    return []


def require_native_origin(url):
    parsed=urlsplit(url)
    if (parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or parsed.port is None
            or parsed.username or parsed.password or parsed.path not in ('','/')
            or parsed.query or parsed.fragment):
        raise ValueError('Exactly the leased loopback native service is required')
    return url.rstrip('/')


def full_http(url,directory,name,deadline):
    """Raw native failure bytes and the first error are preserved as well."""
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    if (directory/(name+'.receipt.json')).exists():raise ValueError('Reference receipt is immutable')
    remaining=deadline-time.monotonic()
    if remaining<=0:raise TimeoutError('Original absolute reference deadline elapsed')
    row={'requested_url':url,'native_only':True,'external_fallback':False}
    data=b''
    try:
        try:response=urlopen(Request(url,headers={'Accept':'application/json'}),timeout=min(30,remaining))
        except HTTPError as error:response=error
        with response:
            row['http_status']=response.status
            chunks=[]
            while True:
                if time.monotonic()>=deadline:raise TimeoutError('Original absolute reference deadline elapsed')
                data=response.read(65536)
                if not data:break
                chunks.append(data)
            data=b''.join(chunks)
        row.update(raw_body_sha256=hashlib.sha256(data).hexdigest(),raw_body_bytes=len(data),raw_body_file=name+'.body')
        (directory/(name+'.body')).write_bytes(data)
        if row['http_status']!=200:raise ValueError('Native reference service returned HTTP '+str(row['http_status']))
        row['value']=json.loads(data)
        row['status']='complete_native_response'
    except Exception as error:
        row.update(status='native_reference_unknown',first_error={'type':type(error).__name__,'message':str(error)})
        if 'raw_body_sha256' not in row:
            # A partial transport body cannot be silently discarded or treated
            # as the complete native endpoint response.
            partial=b''.join(chunks) if 'chunks' in locals() else data
            (directory/(name+'.partial')).write_bytes(partial)
            row.update(partial_body_file=name+'.partial',partial_bytes=len(partial),partial_sha256=hashlib.sha256(partial).hexdigest())
    (directory/(name+'.receipt.json')).write_text(json.dumps(row,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    return row


def reference_inventory(site,candidates,directory,*,deadline):
    if site.domain!='map' or site.with_geographic_baseline is not True or site.track_changes is not True:
        raise ValueError('Actual complete normal geographic factory required')
    site.reset_guard.require_unchanged()
    before=site.fingerprint()
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    origin=require_native_origin(site.search_url)
    routers={p:require_native_origin(v) for p,v in site.route_urls.items()}
    if set(routers)!=set(('car','bike','foot')) or len(set(routers.values()))!=3:
        raise ValueError('Independent native car/bike/foot service roles required')
    queries=sorted({q for c in candidates for q in original_queries(c['endpoint_request'])})
    geocodes={}
    for index,q in enumerate(queries):
        receipt=full_http(origin+'/search?'+urlencode({'q':q,'format':'jsonv2',
            'addressdetails':1,'namedetails':1,'extratags':1,'limit':50}),directory/'geocodes',str(index),deadline)
        records=receipt.get('value')
        complete=receipt['status']=='complete_native_response' and isinstance(records,list)
        if complete:
            for record in records:
                if (not isinstance(record,dict) or type(record.get('osm_id')) is not int
                        or record.get('osm_type') not in ('node','way','relation') or not record.get('display_name')
                        or not isinstance(record.get('address'),dict)):
                    complete=False;break
                point([record['lat'],record['lon']])
        geocodes[q]={'query':q,'native_receipt':str(Path('geocodes')/(str(index)+'.receipt.json')),
            'native_receipt_sha256':fingerprint(receipt),'full_records':records if complete else None,
            'status':'full_identity_candidates_require_declaration' if complete and records else 'native_geographic_coverage_unavailable',
            'candidate_identities':[{'requested_query':q,'full_geocode_record':deepcopy(r),'full_geocode_sha256':fingerprint(r)} for r in records] if complete else [],
            'first_result_only_accepted':False,'task_admitted':False}
    sources=[]
    for c in candidates:
        request=c['endpoint_request'];kind=request['kind'];row={
            'source_task_id':c['source_task_id'],'goal':c['goal'],'original_start_path':c['start_path'],
            'candidate_binding_sha256':fingerprint(c),'normal_admitted':False,'actor_attempts':0,'api_calls':0,
            'endpoint_policy':deepcopy(request),'full_identity_queries':original_queries(request)}
        if kind=='exact_points':
            pair=request['pair']
            if not isinstance(pair,list) or len(pair)!=2:raise ValueError('Complete original coordinate pair required')
            pair=[[str(v) for v in point(p)] for p in pair]
            refs=[]
            for mode in c['allowed_modes']:
                coordinates=';'.join(p[1]+','+p[0] for p in pair)
                url=routers[mode]+'/route/v1/driving/'+coordinates+'?overview=false&geometries=polyline&steps=true'
                receipt=full_http(url,directory/'routes',c['source_task_id']+'-'+mode,deadline)
                item={'profile':mode,'pair':deepcopy(pair),'native_receipt_sha256':fingerprint(receipt),
                    'full_native_response':receipt.get('value'),'complete':False}
                if receipt['status']=='complete_native_response':
                    try:complete_route(receipt['value']);item['complete']=True
                    except Exception as error:item['first_error']={'type':type(error).__name__,'message':str(error)}
                refs.append(item)
            row.update(status='exact_full_backend_references_captured' if refs and all(v['complete'] for v in refs) else 'native_route_coverage_unavailable',references=refs)
        elif original_queries(request):
            row['status']='independent_full_named_identity_selection_required'
            if any(geocodes[q]['status']=='native_geographic_coverage_unavailable' for q in row['full_identity_queries']):
                row['status']='native_geographic_coverage_unavailable'
        else:
            row['status']='explicit_original_endpoint_scope_or_initialization_required'
        sources.append(row)
        (directory/'sources.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    site.reset_guard.require_unchanged()
    unchanged=site.fingerprint()==before
    if not unchanged:raise ValueError('Native reference reads changed persistent state')
    result={'version':'map-route37-native-reference-candidates-v1','sources':sources,
        'geocodes':geocodes,'full_normal_baseline':before,'protected_state_unchanged':unchanged,
        'task_admissions':0,'normal_make_session_controls_completed':False,'actor_attempts':0,'api_calls':0,
        'first_result_only_accepted':False,'no_external_service_fallback':True,
        'named_identity_declaration_and_two_cold_normal_controls_required':True}
    (directory/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    return result
