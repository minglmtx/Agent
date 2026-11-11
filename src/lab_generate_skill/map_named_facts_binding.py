"""Full independent native named references for normal facts, never actor data."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qs,urlsplit

from .map_native_identity_declarations import POLICY_SHA,POLICIES,declare_query
from .map_route_normal_capture import fingerprint

VERSION='map-declared-native-named-facts-v1'
KINDS={'named_place_coordinates','named_place_search','initial_where_is_this'}


def validate(contract):
    if contract.get('goal_revision', {}).get('version') == 'native-local-coverage-same-capability-derived-v1':
        from .map_local_coverage_goal_revision import validate as validate_revision
        validate_revision(contract)
        projected = deepcopy(contract)
        projected.pop('goal_revision'); projected['task_text_changed'] = False
        declaration = projected['protocol']['native_identity_declaration']
        declaration['name_in_original_goal'] = declaration.pop('name_in_derived_goal')
        return validate(projected)
    protocol=contract.get('protocol',{});kind=protocol.get('kind')
    if kind not in KINDS:raise ValueError('Declared named/reverse native fact required')
    declaration=protocol.get('native_identity_declaration')
    if not isinstance(declaration,dict) or declaration.get('version')!=VERSION:
        raise ValueError('Explicit named fact interpretation required')
    if (protocol.get('local_finite_interpretation')is not True
        or protocol.get('original_model_judge_equivalence_claim')is not False
        or declaration.get('original_model_judge_equivalence')is not False
        or contract.get('task_text_changed')is not False
        or contract.get('goal_revision') or contract.get('start_revision')):
        raise ValueError('Preserve original fact goal/start with explicit finite local protocol')
    if kind=='initial_where_is_this':
        if declaration!={'version':VERSION,'referent':'actual_original_initial_native_map_center',
                         'original_model_judge_equivalence':False}:
            raise ValueError('Reverse referent must be the actual original initial map center')
        return declaration
    from .map_identity_policy_scope import require_compatible_policy
    query=protocol.get('query');name=declaration.get('name_in_original_goal')
    if (query not in POLICIES or declaration.get('query')!=query
        or not require_compatible_policy(declaration.get('identity_policy_sha256'),[query])
        or declaration.get('identity_policy')!=POLICIES[query]
        or not isinstance(name,str) or not name.strip()
        or name.casefold() not in contract['goal'].casefold()):
        raise ValueError('Exact original named goal and current native semantic policy required')
    # Policies add an explicit published local geographical interpretation.
    # Ranking, guessed coordinates and arbitrary replacement names are absent.
    words=lambda s:re.sub('[^a-z0-9]+',' ',s.casefold()).split()
    if not set(words(name)).issubset(set(words(query))):
        raise ValueError('Declared native query changes the original named target')
    return declaration


def require_reference(contract,proof):
    declaration=validate(contract)
    if contract['protocol']['kind']=='initial_where_is_this':return require_reverse_reference(contract,proof)
    reference=proof.get('actual_named_native_inventory_reference')
    if not isinstance(reference,dict) or set(reference)!={'receipt_file','receipt_sha256','raw_body_file','raw_body_sha256'}:
        raise ValueError('Actual complete named native request/receipt/body references required')
    rows={}
    for field in ('receipt','raw_body'):
        path=Path(reference[field+'_file'])
        if 'actor' in path.parts or not path.is_file():raise ValueError('Actual private native reference missing or actor-supplied')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=reference[field+'_sha256']:
            raise ValueError('Actual named native reference bytes changed')
        rows[field]=raw
    receipt=json.loads(rows['receipt']);body=json.loads(rows['raw_body'])
    u=urlsplit(receipt.get('requested_url',''));params=parse_qs(u.query,keep_blank_values=True)
    expected={'q':[declaration['query']],'format':['jsonv2'],'addressdetails':['1'],
              'namedetails':['1'],'extratags':['1'],'limit':['50']}
    if (u.scheme!='http' or u.hostname!='127.0.0.1' or u.port is None or u.username or u.password
        or u.path!='/search' or u.fragment or params!=expected
        or receipt.get('status')!='complete_native_response' or receipt.get('http_status')!=200
        or receipt.get('native_only')is not True or receipt.get('external_fallback')is not False
        or receipt.get('raw_body_bytes')!=len(rows['raw_body'])
        or receipt.get('raw_body_sha256')!=reference['raw_body_sha256']
        or Path(receipt.get('raw_body_file','')).name!=Path(reference['raw_body_file']).name
        or receipt.get('value')!=body or not isinstance(body,list) or not body):
        raise ValueError('Full exact loopback named request and actual response body required')
    inventory={'status':'full_identity_candidates_require_declaration','full_records':body,
               'native_receipt_sha256':fingerprint(receipt),'full_native_response_receipt':receipt,
               'actual_native_reference':deepcopy(reference)}
    actual=declare_query(declaration['query'],inventory)
    # validate() has proved exact selected-policy equivalence above.
    actual['policy_sha256']=declaration['identity_policy_sha256']
    if actual.get('status')!='unique_semantic_native_identity_declared':
        raise ValueError('Named native geographical identity missing or ambiguous')
    identities=[row for row in body if fingerprint(row)==actual['identity']['full_geocode_sha256']]
    if (len(identities)!=1 or proof.get('native_records')!=identities
        or proof.get('native_identity_declaration')!=actual):
        raise ValueError('Private named record differs from actual independently declared native body')
    return deepcopy(actual)


def require_reverse_reference(contract,proof):
    references=proof.get('actual_initial_reverse_references')
    if not isinstance(references,list) or len(references)!=2:
        raise ValueError('Two actual independent normal reference-context reverse bodies required')
    seen=set()
    for reference in references:
        path=reference.get('body_file')
        if path in seen:raise ValueError('Duplicate reverse reference context')
        seen.add(path);require_reverse_body(contract,proof,reference)
    return declaration_from_reverse(contract)


def require_reverse_body(contract,proof,reference):
    import xml.etree.ElementTree as ET
    from .map_local_capabilities import same_center
    validate(contract)
    if set(reference)!={'body_file','body_sha256','receipt_file','receipt_sha256','actual_rails_request','full_record'}:
        raise ValueError('Exact reverse reference locator/body/actual request required')
    paths=[Path(reference[k+'_file']) for k in ('body','receipt')]
    if any('actor'in p.parts or not p.is_file() for p in paths):
        raise ValueError('Independent actual private reverse references unavailable')
    raw,receipt_bytes=[p.read_bytes()for p in paths]
    if any(hashlib.sha256(b).hexdigest()!=reference[k+'_sha256']for k,b in [('body',raw),('receipt',receipt_bytes)]):
        raise ValueError('Actual reverse response/receipt bytes changed')
    receipt=json.loads(receipt_bytes);u=urlsplit(receipt.get('requested_url',''));params=parse_qs(u.query,keep_blank_values=True)
    request=reference['actual_rails_request'];args=request.get('parameters',{})
    requrl=urlsplit(request.get('url',''));body=request.get('actual_request_body_utf8')
    if not isinstance(body,str):raise ValueError('Full actual native reverse request body unavailable')
    from urllib.parse import parse_qs as parse_form
    url_args=parse_form(requrl.query,keep_blank_values=True);body_args=parse_form(body,keep_blank_values=True)
    merged=dict(url_args)
    for key,value in body_args.items():
        if key in merged and merged[key]!=value:raise ValueError('Conflicting actual reverse URL/body parameters')
        merged[key]=value
    method=request.get('actual_http_method');content=request.get('actual_request_content_type')
    if (method not in ('GET','POST') or (body and (method!='POST' or content!='application/x-www-form-urlencoded'))
        or requrl.scheme!='http' or requrl.hostname!='127.0.0.1' or requrl.port is None or requrl.username or requrl.password or requrl.fragment
        or requrl.path!='/geocoder/search_osm_nominatim_reverse' or request.get('http_status')!=200
        or request.get('actual_request_body_sha256')!=hashlib.sha256(body.encode()).hexdigest()
        or request.get('actual_request_body_bytes')!=len(body.encode()) or merged!=args
        or request.get('actual_url_parameters')!=url_args or request.get('actual_body_parameters')!=body_args
        or request.get('request_only_capture')is not True or request.get('response_body_read_inside_callback')is not False
        or request.get('actual_request_capture_error')):
        raise ValueError('Actual complete original native Rails reverse request required')
    expected={k:args[k]for k in ('lat','lon') if len(args.get(k,[]))==1}
    expected['zoom']=args.get('zoom',['']);expected.update(format=['xml'],**{'accept-language':['en-US,en']})
    if (u.scheme!='http' or u.hostname!='127.0.0.1' or u.port is None or u.username or u.password
        or u.path!='/reverse' or u.fragment or set(expected)!=set(params) or expected!=params
        or receipt.get('http_status')!=200 or receipt.get('native_only')is not True
        or receipt.get('external_fallback')is not False or receipt.get('complete_transport')is not True
        or receipt.get('full_body_sha256')!=reference['body_sha256'] or receipt.get('full_body_bytes')!=len(raw)
        or receipt.get('full_body_file')!=paths[0].name):
        raise ValueError('Complete exact reverse request/response body required')
    results=ET.fromstring(raw).findall('result')
    if len(results)!=1:raise ValueError('One complete actual native reverse object required')
    r=results[0]
    value={'osm_type':r.get('osm_type'),'osm_id':int(r.get('osm_id')),
           'lat':r.get('lat'),'lon':r.get('lon'),'description':r.text}
    if reference['full_record']!=value or proof.get('reverse_full_record')!=value:
        raise ValueError('Full reverse private record differs from original body')
    initial=proof.get('initial_view_identity');zoom=args.get('zoom',[''])[0]
    try:actual=[int(zoom)if zoom else initial[0],float(args['lat'][0]),float(args['lon'][0])]
    except (KeyError,ValueError,TypeError,IndexError)as error:raise ValueError('Original center reverse request missing')from error
    if not initial or not same_center(initial,actual):raise ValueError('Reverse request changes the original native view')
    return deepcopy(reference['full_record'])

def declaration_from_reverse(contract):
    return deepcopy(validate(contract))


def actual_search_checks(proof,timeline):
    """Named search completion needs an actual query, not a bare object URL."""
    from .map_place_identity import identity,public_result_matches
    last=timeline.records[-1]if timeline.records else{}
    request=last.get('native_rails_search_response');lookup=last.get('independent_native_lookup')
    checks={'actual_native_search_requested':False,'actual_complete_native_search_result_identified':False}
    if not isinstance(request,dict)or not isinstance(lookup,dict):return checks
    try:
        url=urlsplit(request['url']);text=request['actual_request_body_utf8'];body=text.encode()
        url_args=parse_qs(url.query,keep_blank_values=True);body_args=parse_qs(text,keep_blank_values=True);merged=dict(url_args)
        for key,value in body_args.items():
            if key in merged and merged[key]!=value:return checks
            merged[key]=value
        method=request['actual_http_method'];content=request['actual_request_content_type']
        checks['actual_native_search_requested']=(url.scheme=='http'and url.hostname=='127.0.0.1'and url.port is not None
            and not url.username and not url.password and not url.fragment and url.path=='/geocoder/search_osm_nominatim'
            and request['http_status']==200 and method in('GET','POST')
            and (not body or(method=='POST'and content=='application/x-www-form-urlencoded'))
            and merged==request['parameters']and url_args==request['actual_url_parameters']and body_args==request['actual_body_parameters']
            and request['actual_request_body_bytes']==len(body)and request['actual_request_body_sha256']==hashlib.sha256(body).hexdigest()
            and merged.get('query')==[last.get('actual_submitted_query')]and bool(last.get('actual_submitted_query'))
            and request.get('request_only_capture')is True and request.get('response_body_read_inside_callback')is False
            and not request.get('actual_request_capture_error'))
        records=proof['native_records'];actual=lookup['full_records']
        from .site_query_rules import same_value
        matched=[r for r in records if any(identity(v)==identity(r)and all(same_value('decimal',v[k],r[k])for k in('lat','lon'))for v in actual)]
        seen=any(public_result_matches(r,result)for r in matched for sample in timeline.records
             if sample.get('place',{}).get('path')=='/search'for result in sample['place'].get('results',[]))
        checks['actual_complete_native_search_result_identified']=bool(matched and seen and lookup.get('new_target_or_search_query_created')is False
             and lookup.get('complete_transport')is True and lookup.get('native_only')is True and lookup.get('external_fallback')is False)
    except(ValueError,KeyError,TypeError,AttributeError):return checks
    return checks


def require_actual_lookup(sample,directory):
    """Reconsume raw exact lookup bytes and receipt at the original locator."""
    value=sample.get('independent_native_lookup')
    if not value:return
    body=Path(value['full_body_file']);body=body if body.is_absolute()else Path(directory)/body
    receipt_file=body.with_suffix(body.suffix+'.receipt.json');raw=body.read_bytes();receipt=json.loads(receipt_file.read_bytes())
    u=urlsplit(value['requested_url']);params=parse_qs(u.query,keep_blank_values=True)
    expected={'osm_ids':[','.join(value['observed_native_object_ids'])],'format':['jsonv2'],'addressdetails':['1'],'namedetails':['1'],'extratags':['1']}
    from .map_place_identity import identity,bounds
    returned=[]
    for row in json.loads(raw):
        kind,number=identity(row);bounds(row);returned.append({'node':'N','way':'W','relation':'R'}[kind]+str(number))
    if len(returned)!=len(set(returned))or set(returned)!=set(value['observed_native_object_ids']):
        raise ValueError('Full native lookup does not identify exactly the observed objects')
    if (u.scheme!='http'or u.hostname!='127.0.0.1'or u.port is None or u.username or u.password or u.fragment
        or u.path!='/lookup'or params!=expected or value.get('http_status')!=200
        or value.get('complete_transport')is not True or value.get('native_only')is not True or value.get('external_fallback')is not False
        or len(raw)!=value['full_body_bytes']or hashlib.sha256(raw).hexdigest()!=value['full_body_sha256']
        or json.loads(raw)!=value['full_records']or receipt!={k:value[k]for k in('requested_url','http_status','full_body_file','full_body_sha256','full_body_bytes','native_only','external_fallback','complete_transport')}):
        raise ValueError('Exact full original native lookup request/body/receipt differs')
