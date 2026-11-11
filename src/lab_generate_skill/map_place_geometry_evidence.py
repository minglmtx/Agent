"""Acquire extra geometry without selecting a geocoder result or changing tasks.

Only an owned native search backend is queried. The full original response and
all identity metadata must match; geometry is additional evidence, not proof
that two objects are equivalent, a route reference or task admission.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode

from .map_native_route_reference_inventory import full_http, require_native_origin
from .map_route_normal_capture import fingerprint


def bind_geometry(native, receipt, raw_body):
    """Check raw-byte custody and exact per-object correspondence, order independent."""
    if (native.get('status') != 'full_identity_candidates_require_declaration'
            or not isinstance(native.get('query'),str) or not native['query'].strip()
            or not isinstance(native.get('full_records'),list) or not native['full_records']
            or receipt.get('native_only')is not True or receipt.get('external_fallback')is not False
            or receipt.get('status')!='complete_native_response' or receipt.get('http_status')!=200
            or receipt.get('raw_body_sha256')!=hashlib.sha256(raw_body).hexdigest()
            or receipt.get('raw_body_bytes')!=len(raw_body)):
        raise ValueError('Complete native original and supplemental response bytes required')
    from urllib.parse import urlsplit,parse_qs
    url=urlsplit(receipt['requested_url']);require_native_origin(url.scheme+'://'+url.netloc)
    expected={'q':[native['query']],'format':['jsonv2'],'addressdetails':['1'],
        'namedetails':['1'],'extratags':['1'],'limit':['50'],'polygon_geojson':['1']}
    if url.path!='/search' or url.fragment or parse_qs(url.query)!=expected:
        raise ValueError('Same native search with explicit geometry only required')
    records=json.loads(raw_body)
    if records!=receipt.get('value') or not isinstance(records,list) or not 0<len(records)<50:
        raise ValueError('Full bounded geometry response differs from raw body')
    def indexed(rows):
        result={}
        for row in rows:
            if not isinstance(row,dict) or row.get('osm_type')not in ('node','way','relation') or type(row.get('osm_id'))is not int:
                raise ValueError('Complete native object identity required')
            key=(row['osm_type'],row['osm_id'])
            if key in result:raise ValueError('Duplicate native object')
            result[key]=row
        return result
    before,after=indexed(native['full_records']),indexed(records)
    if before.keys()!=after.keys():raise ValueError('Native result membership changed while obtaining geometry')
    joined=[]
    for key,original in before.items():
        enriched=after[key];geometry=enriched.get('geojson')
        if {k:v for k,v in enriched.items()if k!='geojson'}!={k:v for k,v in original.items()if k!='geojson'}:
            raise ValueError('Native object metadata changed while obtaining geometry')
        if not isinstance(geometry,dict) or geometry.get('type')not in ('Point','Polygon','MultiPolygon') or not isinstance(geometry.get('coordinates'),list):
            raise ValueError('Complete native point/polygon geometry required')
        joined.append(dict(osm_type=key[0],osm_id=key[1],original_record_sha256=fingerprint(original),
            full_record=deepcopy(enriched)))
    return dict(version='native-place-geometry-evidence-v1',query=native['query'],
        original_query_sha256=fingerprint(native),supplemental_receipt_sha256=fingerprint(receipt),
        objects=joined,provider_order_ignored=True,identity_equivalence_proved=False,
        task_admitted=False,actor_attempts=0,api_calls=0)


def collect_geometry(site,native,directory,*,deadline):
    origin=require_native_origin(site.search_url)
    params={'q':native['query'],'format':'jsonv2','addressdetails':1,'namedetails':1,
        'extratags':1,'limit':50,'polygon_geojson':1}
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    receipt=full_http(origin+'/search?'+urlencode(params),directory,'geometry',deadline)
    # Never accept a receipt without independently reading its recorded raw body.
    name=Path(receipt.get('raw_body_file',''))
    if name.name!=str(name) or not name.name:raise ValueError('Owned native response basename required')
    raw=(directory/name).read_bytes()
    result=bind_geometry(native,receipt,raw)
    from .io_utils import atomic_write_json
    atomic_write_json(directory/'geometry-evidence.json',result)
    return result
