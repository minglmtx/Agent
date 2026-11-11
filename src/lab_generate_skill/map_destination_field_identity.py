"""Named destination existence requires full native semantic evidence.

Nonempty search results alone do not establish a named city. The complete raw
body and original receipt remain private, as do rejected provider candidates.
This module creates no action, native request or admission.
"""
from copy import deepcopy
import hashlib,json,re
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
from .map_route_normal_capture import fingerprint
from .map_native_identity_declarations import declare_query,POLICY_SHA

VERSION='complete-native-named-destination-identity-v1'

def require(contract,proof):
    query=contract['endpoint_request'].get('query')
    if not isinstance(query,str)or not query.strip():
        raise ValueError('A declared literal named destination is required')
    value=proof.get('named_destination_identity')
    if not isinstance(value,dict)or value.get('version')!=VERSION:
        raise ValueError('Complete semantic native destination proof required')
    native=value.get('full_native_query_evidence');review=value.get('semantic_review')
    receipt=value.get('native_receipt');body=value.get('raw_body');receipt_file=value.get('raw_receipt')
    if (not isinstance(native,dict)or native.get('query')!=query
            or not isinstance(receipt,dict)or receipt.get('status')!='complete_native_response'
            or receipt.get('http_status')!=200 or receipt.get('native_only')is not True
            or receipt.get('external_fallback')is not False
            or native.get('native_receipt_sha256')!=fingerprint(receipt)
            or not isinstance(body,dict)or not isinstance(receipt_file,dict)):
        raise ValueError('Original full named query and native transport must agree')
    u=urlsplit(receipt.get('requested_url',''))
    from .map_native_route_reference_inventory import require_native_origin
    require_native_origin(u.scheme+'://'+u.netloc)
    args=parse_qs(u.query,keep_blank_values=True)
    if (u.path!='/search'or u.fragment or args!= {'q':[query],'format':['jsonv2'],
            'addressdetails':['1'],'namedetails':['1'],'extratags':['1'],'limit':['50']}):
        raise ValueError('Exact full native destination request parameters required')
    def original_bytes(locator):
        if set(locator)!= {'file','sha256','bytes'}or not re.fullmatch(r'[0-9a-f]{64}',str(locator['sha256'])):
            raise ValueError('Complete original file/byte/hash locator required')
        path=Path(locator['file'])
        if 'actor'in path.parts or 'actor'in path.resolve().parts:
            raise ValueError('Actor output cannot provide native destination identity')
        from .original_reference_bytes import read_bytes
        raw=read_bytes(locator, proof)
        if len(raw)!=locator['bytes']or hashlib.sha256(raw).hexdigest()!=locator['sha256']:
            raise ValueError('Original destination reference bytes changed')
        return raw
    try:
        raw=original_bytes(body);raw_receipt=original_bytes(receipt_file)
    except OSError as e:raise ValueError('Original full native destination body/receipt unavailable')from e
    if (json.loads(raw)!=native.get('full_records')or json.loads(raw)!=receipt.get('value')
            or json.loads(raw_receipt)!=receipt or len(raw)!=receipt.get('raw_body_bytes')
            or hashlib.sha256(raw).hexdigest()!=receipt.get('raw_body_sha256')):
        raise ValueError('All native destination body records and receipt must remain exact')
    actual=declare_query(query,native)
    from .map_destination_field_goal_revision import same_reviewed_policy
    if not isinstance(review,dict) or not same_reviewed_policy(review.get('policy_sha256'),query):
        raise ValueError('Native destination policy changed')
    if {k:v for k,v in review.items() if k!='policy_sha256'}!={k:v for k,v in actual.items() if k!='policy_sha256'}:
        raise ValueError('Native destination semantic review changed')
    matching=[r for r in actual.get('all_native_record_checks',[])
              if r.get('checks')and all(v is True for v in r['checks'].values())]
    if not matching:
        raise ValueError('Native results do not identify the requested destination '+query)
    candidates=proof.get('destination_identity_candidates')
    expected=[dict(requested_query=query,full_geocode_record=deepcopy(r['full_geocode_record']),
             full_geocode_sha256=r['full_geocode_sha256'],native_reference_receipt_sha256=fingerprint(receipt),
             independent_native_identity_read=True)for r in matching]
    if candidates!=expected:
        raise ValueError('Exactly every semantic destination identity must remain bound')
    return matching

def semantics(contract,proof):
    require(contract,proof)
    value=proof['named_destination_identity'];native=value['full_native_query_evidence']
    receipt=value['native_receipt'];u=urlsplit(receipt['requested_url'])
    # Original files/receipts retain leased absolute URLs and paths. Cross-cold
    # semantic comparison retains full request options and response bytes/data.
    return {'version':VERSION,'query':native['query'],'policy_sha256':value['semantic_review']['policy_sha256'],
       'full_native_records':deepcopy(native['full_records']),
       'all_native_record_checks':deepcopy(value['semantic_review']['all_native_record_checks']),
       'matching_native_record_count':value['semantic_review']['matching_native_record_count'],
       'request_path':u.path+'?'+u.query,
       'transport':{k:deepcopy(receipt[k])for k in ('status','http_status','native_only','external_fallback','raw_body_sha256','raw_body_bytes','value')},
       'first_provider_rank_used':False,'actor_output_used':False}
