"""Retain separately identified native representations of one named place.

This declares candidate endpoints, never polygon equality or task admission.
It does not pick a provider's first result. Every accepted record is retained.
"""
from copy import deepcopy
import re
from .map_native_endpoint_alias import BASE_CHECKS, fingerprint, native_geography


def declare_named_endpoint_alternatives(review):
    native=review.get('full_native_query_evidence',{})
    records=native.get('full_records')
    inspected=review.get('all_native_record_checks')
    if (review.get('status')!='ambiguous_native_identity'
            or native.get('query')!=review.get('query')
            or native.get('status')!='full_identity_candidates_require_declaration'
            or not re.fullmatch(r'[0-9a-f]{64}',str(native.get('native_receipt_sha256','')))
            or review.get('first_result_rank_used') is not False
            or review.get('actor_or_later_published_step_used') is not False
            or not isinstance(records,list) or not isinstance(inspected,list)
            or len(records)!=len(inspected)):
        raise ValueError('Complete independent native semantic review required')
    accepted=[]
    for record,check in zip(records,inspected):
        flags=check.get('checks',{})
        if (check.get('full_geocode_record')!=record
                or check.get('full_geocode_sha256')!=fingerprint(record)
                or not isinstance(flags,dict) or not BASE_CHECKS<=flags.keys()
                or any(type(value)is not bool for value in flags.values())):
            raise ValueError('Complete native identity and every rejection must be retained')
        if all(flags.values()):accepted.append(record)
    identities=[(r.get('osm_type'),r.get('osm_id'))for r in accepted]
    if (len(accepted)<2 or len(accepted)!=review.get('matching_native_record_count')
            or len(set(identities))!=len(identities)
            or any(kind not in ('node','way','relation')or type(ident)is not int or ident<=0
                   for kind,ident in identities)):
        raise ValueError('Distinct complete native object identities required')
    anchors={}
    for key in ('wikidata','wikipedia'):
        values=[r.get('extratags',{}).get(key)for r in accepted]
        if any(not isinstance(v,str)or not v.strip()for v in values)or len(set(values))!=1:
            raise ValueError('Every native alternative must identify the same named place')
        anchors[key]=values[0]
    if not re.fullmatch(r'Q[1-9][0-9]*',anchors['wikidata']):
        raise ValueError('Explicit native Wikidata place identity required')
    geography=[native_geography(r)for r in accepted]
    bounds=[b for _,b in geography]
    if (max(b[0]for b in bounds)>=min(b[1]for b in bounds)
            or max(b[2]for b in bounds)>=min(b[3]for b in bounds)):
        raise ValueError('Disjoint native geographic extents cannot resolve the place')
    return {'version':'native-same-place-endpoint-alternatives-v1',
            'query':review['query'],'shared_native_anchors':anchors,
            'alternatives':[{'point':[str(v)for v in p],'identities':[deepcopy(record)],
                             'kind':'distinct_native_same_place_representation',
                             'normal_admission':False,'provider_rank_used':False}
                            for record,(p,_)in zip(accepted,geography)],
            'full_native_query_evidence':deepcopy(native),
            'all_native_record_checks':deepcopy(inspected),
            'coordinates_claimed_equal':False,'polygons_claimed_equal':False,
            'selected_osm_id':None,'normal_admission':False}
