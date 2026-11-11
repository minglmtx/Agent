"""Read-only native object and OSRM metadata; no task judgment or admission."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import re
from urllib.parse import parse_qs, urlsplit

from lab_generate_skill.map_route_normal_capture import fingerprint, point

VERSION = 'full-original-route-native-metadata-diagnostic-v1'


def object_keys(geocodes):
    keys = set()
    for query, row in geocodes.items():
        records = row.get('full_records')
        if row.get('status') != 'full_identity_candidates_require_declaration':
            continue
        if not isinstance(records, list):
            raise ValueError('Full native candidate records are required')
        for record in records:
            kind, ident = record.get('osm_type'), record.get('osm_id')
            if kind not in ('node', 'way', 'relation') or type(ident) is not int or ident <= 0:
                raise ValueError('Actual native object identity is malformed')
            keys.add((kind, ident))
    return [[kind, ident] for kind, ident in sorted(keys)]


def annotated_nodes(body):
    from lab_generate_skill.map_route_normal_capture import complete_route
    route = complete_route(body)
    values = route['legs'][0].get('annotation', {}).get('nodes')
    if (not isinstance(values, list) or len(values) < 2
            or any(type(value) is not int or value <= 0 for value in values)):
        raise ValueError('The native route did not provide a complete node-annotation chain')
    return list(values)


def exact_native_endpoint(query, native, review):
    """Retain all identities; a shared endpoint never asserts object equality."""
    if review.get('full_native_query_evidence') != native or review.get('query') != query:
        raise ValueError('Semantic review does not bind this complete native query')
    inspected = review.get('all_native_record_checks')
    records = native.get('full_records')
    if not isinstance(records, list) or not isinstance(inspected, list) or len(records) != len(inspected):
        raise ValueError('All actual native records, including rejections, are required')
    matches = []
    for record, row in zip(records, inspected):
        if row.get('full_geocode_record') != record or row.get('full_geocode_sha256') != fingerprint(record):
            raise ValueError('The complete native record or checksum changed')
        checks = row.get('checks', {})
        if checks and all(value is True for value in checks.values()):
            matches.append(deepcopy(record))
    if len(matches) == 1 and review['status'] == 'unique_semantic_native_identity_declared':
        pair = [str(value) for value in point([matches[0]['lat'], matches[0]['lon']])]
        return {'point': pair, 'identities': matches, 'kind': 'one_complete_native_identity',
                'normal_admission': False, 'provider_rank_used': False}
    if review.get('status') == 'ambiguous_native_identity':
        from .map_native_endpoint_alias import declare_coincident_routing_alias
        group = declare_coincident_routing_alias(review)
        return {'point': group['native_point'], 'identities': group['matching_full_native_records'],
                'kind': 'review_candidate_exact_coincident_native_aliases',
                'complete_alias_declaration': group, 'normal_admission': False,
                'provider_rank_used': False, 'selected_osm_id': None}
    raise ValueError('No unique or exactly coincident native endpoint is available')


def retained_original_pair(contract):
    """Recover both points from the declared original first route, without inference."""
    request = contract['endpoint_request']
    if (request.get('kind') != 'replace_one_endpoint'
            or request.get('changed') not in ('origin', 'destination')
            or request.get('source') != 'explicit_original_goal_and_original_first_route_url'
            or request.get('unchanged_peer_backend_point_must_remain_exact') is not True
            or contract.get('initialization_revision') is not None
            or contract.get('initial_route_required') != contract.get('start_path')):
        raise ValueError('Exact original one-endpoint replacement declaration required')
    url = urlsplit(contract['start_path'])
    query = parse_qs(url.query, keep_blank_values=True)
    if (url.scheme or url.netloc or url.path != '/directions'
            or len(query.get('route', [])) != 1 or len(query.get('engine', [])) != 1):
        raise ValueError('Unambiguous original local direction route required')
    mode = {'fossgis_osrm_car': 'car', 'fossgis_osrm_bike': 'bike',
            'fossgis_osrm_foot': 'foot'}.get(query['engine'][0])
    if mode is None or contract.get('allowed_modes') != [mode]:
        raise ValueError('Original route transport must be retained exactly')
    def parse_pair(text):
        if not isinstance(text, str) or len(text.split(';')) != 2:
            raise ValueError('Two complete original route points required')
        return [point(item.split(',')) for item in text.split(';')]
    original = parse_pair(query['route'][0])
    declared = parse_pair(request.get('retained_pair'))
    if original != declared or original[0] == original[1]:
        raise ValueError('Retained pair differs from the original first route')
    return [[str(value) for value in row] for row in original]


def diagnostic_pair(contract, inventory, reviews):
    request = contract['endpoint_request']
    kind = request['kind']
    if kind == 'exact_points':
        return {'pair': [[str(v) for v in point(p)] for p in request['pair']],
                'scope': 'declared_original_or_published_first_initial_pair',
                'initialization_revision': deepcopy(contract['initialization_revision'])}
    if kind == 'replace_one_endpoint':
        initial = retained_original_pair(contract)
        query = request.get('query')
        if not isinstance(query, str) or not query.strip():
            raise ValueError('Explicit requested replacement location required')
        endpoint = exact_native_endpoint(query, inventory['geocodes'][query], reviews[query])
        changed = 0 if request['changed'] == 'origin' else 1
        pair = deepcopy(initial)
        pair[changed] = endpoint['point']
        if point(pair[0]) == point(pair[1]) or point(pair[changed]) == point(initial[changed]):
            raise ValueError('Replacement must change the declared endpoint to a distinct location')
        return {'pair': pair, 'initial_pair': initial, 'replacement_endpoint': endpoint,
                'changed_endpoint_index': changed, 'retained_endpoint_index': 1-changed,
                'source_initial_route': contract['start_path'], 'requested_queries': [query],
                'scope': 'original_one_endpoint_replacement', 'normal_admission': False,
                'initialization_revision': None, 'selected_osm_id': None}
    if kind not in ('named_places', 'reverse_named_initial_route'):
        raise ValueError('Original task has no complete declared two-endpoint pair')
    queries = request['queries'] if kind == 'named_places' else request['initial_queries']
    if not isinstance(queries, list) or len(queries) != 2:
        raise ValueError('Complete original named pair required')
    endpoints = [exact_native_endpoint(q, inventory['geocodes'][q], reviews[q]) for q in queries]
    pair = [endpoint['point'] for endpoint in endpoints]
    if point(pair[0]) == point(pair[1]):
        raise ValueError('The original native endpoints are not distinct')
    return {'pair': pair, 'endpoints': endpoints, 'requested_queries': list(queries),
            'scope': 'original_named_route' if kind == 'named_places' else 'explicit_original_named_initial_route_candidate',
            'initialization_revision': deepcopy(contract['initialization_revision']),
            'normal_admission': False, 'selected_osm_id': None}


def diagnostic_pairs(contract, inventory, reviews):
    """Keep all explicitly linked native place variants, never choose by rank."""
    request=contract['endpoint_request'];kind=request['kind']
    if kind not in ('named_places','reverse_named_initial_route','replace_one_endpoint'):
        return [diagnostic_pair(contract,inventory,reviews)]
    initial=retained_original_pair(contract) if kind=='replace_one_endpoint' else None
    queries=([request.get('query')] if initial is not None else
             request['queries'] if kind=='named_places' else request['initial_queries'])
    if len(queries)!=(1 if initial is not None else 2) or any(not isinstance(q,str)or not q.strip()for q in queries):
        raise ValueError('Complete original endpoint queries required')
    groups=[];declarations=[]
    for query in queries:
        native=inventory['geocodes'][query];review=reviews[query]
        try:
            groups.append([exact_native_endpoint(query,native,review)])
        except ValueError:
            if review.get('full_native_query_evidence')!=native or review.get('query')!=query:
                raise ValueError('Named alternatives do not bind the actual query')
            from .map_named_endpoint_alternatives import declare_named_endpoint_alternatives
            declaration=declare_named_endpoint_alternatives(review)
            declarations.append(declaration)
            groups.append(declaration['alternatives'])
    from itertools import product
    results=[]
    for endpoints in product(*groups):
        if initial is not None:
            changed=0 if request['changed']=='origin' else 1
            pair=deepcopy(initial);pair[changed]=endpoints[0]['point']
            if point(pair[changed])==point(initial[changed]):
                raise ValueError('Named alternative would make the original task a no-op')
        else:
            pair=[endpoint['point']for endpoint in endpoints]
        if point(pair[0])==point(pair[1]):
            raise ValueError('Named alternatives contain a degenerate route')
        results.append({'pair':deepcopy(pair),'endpoints':deepcopy(list(endpoints)),
            'requested_queries':list(queries),'initial_pair':deepcopy(initial),
            'scope':'all_independently_identified_native_place_variants',
            'same_place_alternative_declarations':deepcopy(declarations),
            'initialization_revision':deepcopy(contract.get('initialization_revision')),
            'normal_admission':False,'selected_osm_id':None,'provider_rank_used':False})
    return results


def native_object_program(keys, route_nodes, filename):
    if (not isinstance(keys, list) or any(not isinstance(key, list) or len(key) != 2
            or key[0] not in ('node', 'way', 'relation') or type(key[1]) is not int or key[1] <= 0 for key in keys)
            or len(keys) != len({tuple(key) for key in keys})):
        raise ValueError('Unique complete actual native identity keys required')
    if not isinstance(route_nodes, list) or any(type(v) is not int or v <= 0 for v in route_nodes):
        raise ValueError('Actual annotated native nodes required')
    if not re.fullmatch(r'native-route-metadata-[a-z0-9_-]+\.json', filename):
        raise ValueError('A private bounded metadata output name is required')
    return '''ActiveRecord::Base.connection.execute("SET default_transaction_read_only=on")
requested = __KEYS__
route_node_ids = __NODES__
def tags(records)
  records.to_h { |t| [t.k, t.v] }
end
def node_record(node)
  { :id => node.id.to_s, :version => node.version.to_s, :visible => node.visible?,
    :latitude_integer => node.latitude, :longitude_integer => node.longitude,
    :tags => tags(node.node_tags) }
end
nodes = Node.where(:id => requested.select { |k| k[0] == "node" }.map { |k| k[1] }).includes(:node_tags).to_a
ways = Way.where(:id => requested.select { |k| k[0] == "way" }.map { |k| k[1] }).preload(:way_tags, :way_nodes).to_a
relations = Relation.where(:id => requested.select { |k| k[0] == "relation" }.map { |k| k[1] }).preload(:relation_tags, :relation_members).to_a
route_memberships = WayNode.where(:node_id => route_node_ids).to_a
route_way_ids = route_memberships.map { |wn| wn.id[0] }.uniq
route_ways = Way.where(:id => route_way_ids).preload(:way_tags, :way_nodes).to_a
ways = (ways + route_ways).uniq(&:id)
geometry_node_ids = ways.flat_map { |w| w.way_nodes.map(&:node_id) }.uniq
geometry_nodes = Node.where(:id => geometry_node_ids).includes(:node_tags).to_a
present = nodes.map { |n| ["node", n.id] } + ways.map { |w| ["way", w.id] } + relations.map { |r| ["relation", r.id] }
payload = {
  :version => __VERSION__, :requested_identities => requested,
  :missing_requested_identities => requested - present,
  :nodes => nodes.map { |n| node_record(n) },
  :ways => ways.map { |w| { :id => w.id.to_s, :version => w.version.to_s, :visible => w.visible?,
    :nodes => w.way_nodes.map { |wn| wn.node_id.to_s }, :tags => tags(w.way_tags) } },
  :relations => relations.map { |r| { :id => r.id.to_s, :version => r.version.to_s, :visible => r.visible?,
    :members => r.relation_members.map { |m| { :type => m.member_type.downcase, :ref => m.member_id.to_s, :role => m.member_role } },
    :tags => tags(r.relation_tags) } },
  :way_geometry_nodes => geometry_nodes.map { |n| node_record(n) },
  :missing_way_geometry_node_ids => geometry_node_ids.map(&:to_s) - geometry_nodes.map { |n| n.id.to_s },
  :actual_route_annotation_node_ids => route_node_ids,
  :route_node_way_memberships => route_memberships.map { |wn| { :way_id => wn.id[0].to_s, :sequence_id => wn.id[1], :node_id => wn.node_id.to_s } },
  :database_transaction_read_only => true, :relation_child_geometry_claimed_complete => false,
  :first_provider_rank_used => false, :normal_admission => false
}
File.write(__OUTPUT__, JSON.generate(payload))
'''.replace('__KEYS__', json.dumps(keys)).replace('__NODES__', json.dumps(sorted(set(route_nodes)))).replace('__VERSION__', json.dumps(VERSION)).replace('__OUTPUT__', json.dumps('/state/' + filename))


def capture_objects(site, geocodes, route_nodes, directory, *, seconds):
    from lab_generate_skill.io_utils import atomic_write_json
    keys = object_keys(geocodes)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    filename = 'native-route-metadata-all-candidates.json'
    state = site.state / 'frontend'
    program = state / 'native-route-metadata-all-candidates.rb'
    source = native_object_program(keys, route_nodes, filename)
    with program.open('x') as stream:
        stream.write(source)
    with (directory / 'exact-native-program.rb').open('x') as stream:
        stream.write(source)
    command = list(site.rails_command)
    command = command[:command.index('server')] + ['runner', '/state/' + program.name]
    error = None
    receipt = {'program_sha256': hashlib.sha256(source.encode()).hexdigest(),
               'requested_identity_count': len(keys), 'native_direct_database_read': True,
               'http_response_used_as_database_reference': False, 'normal_admission': False}
    raw = None
    try:
        site.run(command, 'direct_native_route_metadata', seconds)
    except BaseException as failure:
        error = failure
        receipt['first_error'] = {'type': type(failure).__name__, 'message': str(failure)}
    finally:
        output = state / filename
        if output.is_file():
            raw = output.read_bytes()
            with (directory / filename).open('xb') as stream:
                stream.write(raw)
            receipt.update(body_sha256=hashlib.sha256(raw).hexdigest(), body_bytes=len(raw),
                           preserved_before_parse=True)
        atomic_write_json(directory / 'capture.json', receipt)
    if error is not None:
        raise error
    if raw is None:
        raise ValueError('Direct native database output is unavailable')
    value = json.loads(raw)
    if (value.get('version') != VERSION or value.get('requested_identities') != keys
            or value.get('database_transaction_read_only') is not True
            or value.get('normal_admission') is not False):
        raise ValueError('Direct native metadata is missing or source scope changed')
    return value


def adjacent_native_way_sets(annotation_nodes, metadata):
    """Keep every exact sequence match; absent or overlapping paths stay visible."""
    actual = metadata.get('actual_route_annotation_node_ids')
    if not isinstance(actual, list) or not set(annotation_nodes) <= set(actual):
        raise ValueError('Way membership inventory must cover this entire actual route chain')
    ways = metadata.get('ways')
    if not isinstance(ways, list):
        raise ValueError('Complete native ways are unavailable')
    edges = {}
    for way in ways:
        ident = way.get('id')
        nodes = way.get('nodes')
        tags = way.get('tags')
        if (not isinstance(ident, str) or not re.fullmatch(r'[1-9][0-9]*', ident)
                or not isinstance(nodes, list) or not nodes or not isinstance(tags, dict)
                or any(not isinstance(k, str) or not isinstance(v, str) for k, v in tags.items())):
            raise ValueError('Full exact native way sequence and tags are required')
        if way.get('visible') is not True:
            continue
        for left, right in zip(nodes, nodes[1:]):
            key = tuple(sorted((str(left), str(right))))
            edges.setdefault(key, []).append({'way_id': ident, 'tags': deepcopy(tags)})
    result = []
    for left, right in zip(annotation_nodes, annotation_nodes[1:]):
        result.append({'from_osm_node': left, 'to_osm_node': right,
                       'all_exact_native_way_candidates': deepcopy(edges.get(tuple(sorted((str(left), str(right)))), []))})
    return {'all_actual_annotation_edges': result,
            'missing_exact_edge_count': sum(not row['all_exact_native_way_candidates'] for row in result),
            'ambiguous_exact_edge_count': sum(len(row['all_exact_native_way_candidates']) > 1 for row in result),
            'highway_class_chosen': False, 'normal_admission': False}
