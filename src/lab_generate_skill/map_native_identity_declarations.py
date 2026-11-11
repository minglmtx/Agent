"""Declare only unique semantic identities from complete native query records.

No geocoder ranking, actor output, published later step, coordinate guess or
external fallback is used. Ambiguous/missing/malformed native results stay
unresolved. Every full returned record and every rejection remains in evidence.
"""
from copy import deepcopy
import re
from lab_generate_skill.map_route_normal_capture import fingerprint, point

VERSION = 'unique-full-native-semantic-identity-v2'


def normalized(value):
    return re.sub(r'[^a-z0-9]+', ' ', value.casefold()).strip() if isinstance(value, str) else ''


def city(names, state):
    return {'names': names, 'country_code': 'us', 'state': [state], 'category': ['place', 'boundary'],
            'address_type': ['city', 'town', 'borough', 'city_district', 'suburb'], 'type': ['city', 'town', 'administrative', 'borough', 'suburb']}


def borough(names):
    return {'names': names, 'country_code': 'us', 'state': ['New York'], 'category': ['place', 'boundary'],
            'address_type': ['borough', 'city_district', 'suburb', 'administrative'], 'type': ['administrative', 'borough', 'suburb']}


def landmark(names, category_types, district):
    return {'names': names, 'country_code': 'us', 'state': ['New York'], 'category_types': category_types,
            'district_any': district}


MANHATTAN = {'city_district': ['Manhattan'], 'borough': ['Manhattan'], 'suburb': ['Manhattan'], 'county': ['New York County']}
POLICIES = {
    'Chicago': city(['Chicago'], 'Illinois'), 'Detroit': city(['Detroit'], 'Michigan'),
    'Miami': city(['Miami'], 'Florida'), 'Orlando': city(['Orlando'], 'Florida'),
    'New York, NY': city(['New York', 'New York City', 'City of New York'], 'New York'),
    'New York City': city(['New York', 'New York City', 'City of New York'], 'New York'),
    'Washington, DC': city(['Washington', 'Washington DC', 'Washington D C', 'District of Columbia'], 'District of Columbia'),
    'Washington DC': city(['Washington', 'Washington DC', 'Washington D C', 'District of Columbia'], 'District of Columbia'),
    'Rochester': city(['Rochester'], 'New York'), 'Syracuse': city(['Syracuse'], 'New York'),
    'Buffalo': city(['Buffalo'], 'New York'), 'Boston': city(['Boston'], 'Massachusetts'),
    'Los Angeles': city(['Los Angeles'], 'California'), 'San Diego': city(['San Diego'], 'California'),
    'San Francisco': city(['San Francisco'], 'California'), 'Oakland': city(['Oakland'], 'California'),
    'Manhattan': borough(['Manhattan']), 'Brooklyn': borough(['Brooklyn']),
    'Upper Manhattan': {'names': ['Upper Manhattan'], 'country_code': 'us', 'state': ['New York'],
        'category': ['place', 'boundary'], 'address_type': ['neighbourhood', 'quarter', 'suburb', 'city_district'],
        'type': ['neighbourhood', 'quarter', 'suburb', 'administrative']},
    'Lower Manhattan': {'names': ['Lower Manhattan'], 'country_code': 'us', 'state': ['New York'],
        'category': ['place', 'boundary'], 'address_type': ['neighbourhood', 'quarter', 'suburb', 'city_district'],
        'type': ['neighbourhood', 'quarter', 'suburb', 'administrative']},
    'Central Park': landmark(['Central Park'], [['leisure', 'park']], MANHATTAN),
    'Times Square': landmark(['Times Square'], [['place', 'square'], ['place', 'locality'], ['highway', 'pedestrian'], ['tourism', 'attraction']], MANHATTAN),
    'Times Square, New York': landmark(['Times Square'], [['place', 'square'], ['place', 'locality'], ['highway', 'pedestrian'], ['tourism', 'attraction']], MANHATTAN),
    'Empire State Building': landmark(['Empire State Building'], [['building', 'yes'], ['building', 'commercial'], ['man_made', 'tower'], ['tourism', 'attraction']], MANHATTAN),
    'Rockefeller Center': landmark(['Rockefeller Center'], [['tourism', 'attraction']], MANHATTAN),
    'Brooklyn Bridge': landmark(['Brooklyn Bridge'], [['man_made', 'bridge'], ['bridge', 'yes'], ['highway', 'pedestrian'], ['highway', 'primary'], ['tourism', 'attraction']],
        {'city': ['New York', 'New York City', 'City of New York'], 'county': ['New York County', 'Kings County'], 'city_district': ['Manhattan', 'Brooklyn']}),
    'JFK Airport': landmark(['JFK', 'JFK Airport', 'John F Kennedy International Airport'], [['aeroway', 'aerodrome']],
        {'city_district': ['Queens'], 'county': ['Queens County'], 'city': ['New York', 'New York City', 'City of New York']}),
}
POLICY_SHA = fingerprint({'version': VERSION, 'policies': POLICIES,
    'missing_addresstype_resolution':'explicit_native_address_role_or_place_extratag_same_semantic_name',
    'present_addresstype_resolution':'must_match_declared_role_no_fallback',
    'native_namedetail_aliases':['name','name:en','official_name','short_name','alt_name','_place_name'],
    'no_provider_rank_or_implicit_default':True})


def native_address_role(record, policy):
    """Support the actual snapshot's old Nominatim representation explicitly.

    Modern addresstype remains authoritative when present. The older native
    response omits that field; its complete explicit address role and native
    place/linked_place tags can establish the same semantic category. This
    never infers a city merely from its query name or provider importance.
    """
    roles=policy['address_type']
    if 'addresstype'in record:
        return record['addresstype']in roles
    address=record.get('address',{})
    expected={normalized(v)for v in policy['names']}
    if not isinstance(address,dict):return False
    explicit=any(normalized(address.get(role))in expected for role in roles)
    extras=record.get('extratags',{})
    if not isinstance(extras,dict):extras={}
    declared_place=any(extras.get(k)in roles for k in('place','linked_place'))
    # The caller separately verifies feature class/type, identity, geographic
    # region, country, coordinates, and semantic name. An address role alone
    # cannot turn a university on Washington Street into Washington DC.
    return explicit or declared_place


def match_record(query, record):
    policy = POLICIES.get(query)
    checks = {}
    if policy is None:
        return {'query_policy_declared': False}
    if not isinstance(record, dict):
        return {'native_record_complete': False}
    address = record.get('address')
    details = record.get('namedetails', {})
    names = [record.get('name'), record.get('display_name', '').split(',', 1)[0]]
    if isinstance(details, dict):
        names += [value for key, value in details.items() if key in ('name', 'name:en', 'official_name', 'short_name', 'alt_name', '_place_name')]
    expected_names = {normalized(x) for x in policy['names']}
    checks['full_native_object_identity'] = (type(record.get('osm_id')) is int and record['osm_id'] > 0
        and record.get('osm_type') in ('node', 'way', 'relation') and bool(record.get('display_name'))
        and isinstance(address, dict))
    try:
        point([record['lat'], record['lon']])
        checks['native_coordinate_valid'] = True
    except (ValueError, KeyError, TypeError):
        checks['native_coordinate_valid'] = False
    checks['requested_semantic_name'] = bool(expected_names & {normalized(x) for x in names if isinstance(x, str)})
    address = address if isinstance(address, dict) else {}
    checks['country'] = normalized(address.get('country_code')) == policy['country_code']
    checks['requested_region'] = normalized(address.get('state')) in {normalized(x) for x in policy['state']}
    category = record.get('category', record.get('class'))
    if 'category_types' in policy:
        checks['requested_feature_kind'] = [category, record.get('type')] in policy['category_types']
    else:
        checks['requested_feature_kind'] = (category in policy['category'] and record.get('type') in policy['type']
            and native_address_role(record,policy))
    if 'district_any' in policy:
        checks['requested_local_district'] = any(normalized(address.get(key)) in {normalized(x) for x in choices}
            for key, choices in policy['district_any'].items())
    return checks


def declare_query(query, native):
    """All matching rows retained; exactly one full object is needed to pin it."""
    records = native.get('full_records')
    if native.get('status') != 'full_identity_candidates_require_declaration' or not isinstance(records, list) or not records:
        return {'query': query, 'status': 'native_geographic_coverage_unavailable', 'policy_sha256': POLICY_SHA,
                'full_native_query_evidence': deepcopy(native), 'first_result_rank_used': False}
    inspected = [{'full_geocode_record': deepcopy(record), 'full_geocode_sha256': fingerprint(record),
                  'checks': match_record(query, record)} for record in records]
    matches = [r for r in inspected if r['checks'] and all(v is True for v in r['checks'].values())]
    # Duplicate copies of a record are retained as ambiguity too: provider output
    # must be unambiguous, not silently reduced to a convenient first row.
    status = 'unique_semantic_native_identity_declared' if len(matches) == 1 else 'ambiguous_native_identity' if matches else 'no_requested_semantic_native_identity'
    result = {'query': query, 'status': status, 'policy_sha256': POLICY_SHA, 'full_native_query_evidence': deepcopy(native),
              'all_native_record_checks': inspected, 'matching_native_record_count': len(matches), 'first_result_rank_used': False,
              'actor_or_later_published_step_used': False}
    if len(matches) == 1:
        chosen = matches[0]
        result['identity'] = {'requested_query': query, 'full_geocode_sha256': chosen['full_geocode_sha256'],
                              'native_receipt_sha256': native['native_receipt_sha256']}
    return result


def declare_sources(candidates, inventory):
    from lab_generate_skill.map_route_normal_runtime import source_binding
    query_reviews = {q: declare_query(q, native) for q, native in inventory['geocodes'].items()}
    declarations = {}
    for c in candidates:
        request = c['endpoint_request']
        if request['kind'] != 'named_places':
            continue
        queries = request['queries']
        reviews = [query_reviews[q] for q in queries]
        if all(r['status'] == 'unique_semantic_native_identity_declared' for r in reviews):
            declarations[c['source_task_id']] = {'source_binding_sha256': fingerprint(source_binding(c)),
                'identity_selection_protocol': VERSION, 'identity_selection_policy_sha256': POLICY_SHA,
                'actor_or_later_published_step_used': False, 'identities': [deepcopy(r['identity']) for r in reviews],
                'full_native_query_reviews': reviews, 'normal_task_admitted': False}
    return {'version': VERSION, 'selection_policy_sha256': POLICY_SHA, 'query_reviews': query_reviews,
            'source_declarations': declarations, 'source_count': len(candidates), 'actor_attempts': 0, 'api_calls': 0, 'task_admissions': 0}
