"""Independent read-only native map API expansion and offline XML diagnostics.

The map endpoint expands bbox nodes through their ways and parent relations.
The direct native database reader follows that published behavior, rather than
using a downloaded API response to construct its own expected geometry. This
optional helper neither grants admission nor changes an actor strategy.
"""
import copy
import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path
import xml.etree.ElementTree as ET
from . import map_osm_artifact as artifact
from .io_utils import atomic_write_json

VERSION = 'map-native-osm-expanded-database-reference-v1'


def rails_reference_program(bounds, output_filename):
    bounds = artifact.bbox(bounds)
    if not isinstance(output_filename, str) or not re.fullmatch(r'osm-expanded-[a-z0-9_-]+\.json', output_filename):
        raise ValueError('A bounded private native-reference filename is required')
    # This is the native Api::MapController#index selection, with private
    # database serialization replacing HTTP rendering. No account fields,
    # writes, inferred target bbox or external endpoint are used.
    return '''ActiveRecord::Base.connection.execute("SET default_transaction_read_only=on")
bounds = BoundingBox.from_s(BOUNDS)
bounds.check_boundaries
bounds.check_size
nodes = Node.bbox(bounds).where(:visible => true).includes(:node_tags).limit(Settings.max_number_of_nodes + 1).to_a
initial_node_ids = nodes.map(&:id)
raise "Native bbox node limit exceeded" if initial_node_ids.length > Settings.max_number_of_nodes
ways = []
list_of_way_nodes = []
unless initial_node_ids.empty?
  way_nodes = WayNode.where(:node_id => initial_node_ids)
  way_ids = way_nodes.map { |wn| wn.id[0] }
  ways = Way.preload(:way_nodes, :way_tags).find(way_ids)
  list_of_way_nodes = ways.flat_map { |way| way.way_nodes.map(&:node_id) }
end
nodes_to_fetch = (list_of_way_nodes.uniq - initial_node_ids) - [0]
nodes += Node.includes(:node_tags).find(nodes_to_fetch) unless nodes_to_fetch.empty?
nodes = nodes.select(&:visible?)
ways = ways.select(&:visible?)
relations = Relation.nodes(nodes.map(&:id)).visible.to_a + Relation.ways(ways.map(&:id)).visible.to_a
relations += Relation.relations(relations.map(&:id)).visible.to_a
relations = relations.uniq(&:id)
raise "Expanded native object budget exceeded" if nodes.length + ways.length + relations.length > MAX_OBJECTS
def tags(records)
  records.to_h { |tag| [tag.k, tag.v] }
end
payload = {
  :version => VERSION_VALUE,
  :bounds => BOUNDS.split(","),
  :initial_node_ids => initial_node_ids.map(&:to_s).sort,
  :nodes => nodes.map { |n| { :id => n.id.to_s, :version => n.version.to_s,
    :lat => (n.latitude / 10000000.0).round(7).to_s, :lon => (n.longitude / 10000000.0).round(7).to_s,
    :tags => tags(n.node_tags) } },
  :ways => ways.map { |w| { :id => w.id.to_s, :version => w.version.to_s,
    :nodes => w.way_nodes.map { |wn| wn.node_id.to_s }, :tags => tags(w.way_tags) } },
  :relations => relations.map { |r| { :id => r.id.to_s, :version => r.version.to_s,
    :members => r.relation_members.map { |m| { :type => m.member_type.downcase,
      :ref => m.member_id.to_s, :role => m.member_role } }, :tags => tags(r.relation_tags) } }
}
File.write(OUTPUT, JSON.generate(payload))
'''.replace('BOUNDS', json.dumps(','.join(bounds))).replace('VERSION_VALUE', json.dumps(VERSION)).replace('MAX_OBJECTS', str(artifact.MAX_OBJECTS)).replace('OUTPUT', json.dumps('/state/' + output_filename))


def _tags(value):
    if not isinstance(value, dict) or any(not isinstance(k, str) or not k or not isinstance(v, str) for k, v in value.items()):
        raise ValueError('Native reference tags are malformed')
    return dict(value)


def canonical_database(value, bounds):
    bounds = artifact.bbox(bounds)
    if not isinstance(value, dict) or set(value) != {'version', 'bounds', 'initial_node_ids', 'nodes', 'ways', 'relations'}:
        raise ValueError('An explicit complete native expansion reference is required')
    if value['version'] != VERSION or artifact.bbox(value['bounds']) != bounds:
        raise ValueError('Native expanded reference version or bounds differ')
    objects = {k: {} for k in ('node', 'way', 'relation')}
    for plural, kind in [('nodes', 'node'), ('ways', 'way'), ('relations', 'relation')]:
        rows = value[plural]
        if not isinstance(rows, list): raise ValueError('Missing native object list')
        for row in rows:
            base = {'id', 'version', 'tags'}
            fields = base | ({'lat', 'lon'} if kind == 'node' else {'nodes'} if kind == 'way' else {'members'})
            if not isinstance(row, dict) or set(row) != fields: raise ValueError('Malformed native exported object schema')
            ident = artifact.positive_id(row['id']); version = artifact.positive_id(row['version'])
            if ident in objects[kind]: raise ValueError('Duplicate native database exported object')
            result = {'version': version, 'tags': _tags(row['tags'])}
            if kind == 'node':
                lat, lon = artifact.coordinate(row['lat']), artifact.coordinate(row['lon'])
                if not -90 <= Decimal(lat) <= 90: raise ValueError('Native node latitude out of range')
                result.update(lat=lat, lon=lon)
            elif kind == 'way':
                if not isinstance(row['nodes'], list) or not row['nodes']: raise ValueError('Native way has no member nodes')
                result['nodes'] = [artifact.positive_id(n) for n in row['nodes']]
            else:
                if not isinstance(row['members'], list): raise ValueError('Missing native relation members')
                members = []
                for member in row['members']:
                    if (not isinstance(member, dict) or set(member) != {'type', 'ref', 'role'} or
                        member['type'] not in objects or not isinstance(member['role'], str)):
                        raise ValueError('Malformed native relation member')
                    members.append(member | {'ref': artifact.positive_id(member['ref'])})
                result['members'] = members
            objects[kind][ident] = result
    if not 1 <= sum(map(len, objects.values())) <= artifact.MAX_OBJECTS or not objects['node']:
        raise ValueError('Expanded native objects unavailable or exceed budget')
    initial = value['initial_node_ids']
    if not isinstance(initial, list) or not initial or len(initial) != len(set(initial)):
        raise ValueError('Independent initial bbox nodes must be explicit and nonempty')
    initial = [artifact.positive_id(i) for i in initial]
    if any(i not in objects['node'] for i in initial): raise ValueError('Initial bbox node missing from native export expansion')
    for way in objects['way'].values():
        if any(i not in objects['node'] for i in way['nodes']): raise ValueError('Native way lacks its exported member node')
    # Relations legitimately refer to objects outside this non-recursive
    # response. Do not invent members or require unrelated members to export.
    west, south, east, north = map(Decimal, bounds)
    if any(not (west <= Decimal(objects['node'][i]['lon']) <= east and south <= Decimal(objects['node'][i]['lat']) <= north) for i in initial):
        raise ValueError('Initial native bbox node is outside requested bounds')
    return {'bounds': bounds, 'objects': objects, 'initial_node_ids': sorted(initial)}


def xml_objects(payload):
    parsed = artifact.parse_xml(payload)  # entities/budgets/strict native structure
    root = ET.fromstring(payload); objects = {k: {} for k in ('node', 'way', 'relation')}
    for item in root:
        if item.tag == 'bounds': continue
        value = {'version': item.attrib['version'], 'tags': {t.attrib['k']: t.attrib['v'] for t in item.findall('tag')}}
        if item.tag == 'node': value.update(lat=artifact.coordinate(item.attrib['lat']), lon=artifact.coordinate(item.attrib['lon']))
        elif item.tag == 'way': value['nodes'] = [n.attrib['ref'] for n in item.findall('nd')]
        else: value['members'] = [dict(n.attrib) for n in item.findall('member')]
        objects[item.tag][item.attrib['id']] = value
    return parsed, objects


def compare_database(payload, bounds, database):
    expected = canonical_database(database, bounds); parsed, actual = xml_objects(payload)
    components = {}; mismatches = {}
    for kind in expected['objects']:
        left, right = actual[kind], expected['objects'][kind]
        components[kind + '_ids'] = set(left) == set(right)
        components[kind + '_content'] = left == right
        mismatches[kind] = {'missing_ids': sorted(set(right) - set(left)), 'extra_ids': sorted(set(left) - set(right)),
                            'changed_ids': sorted(i for i in set(left) & set(right) if left[i] != right[i])}
    components['native_bounds'] = parsed['bounds'] == expected['bounds']
    return {'version': VERSION, 'passed': all(components.values()), 'checks': components, 'mismatches': mismatches,
            'counts': parsed['counts'], 'initial_bbox_nodes': len(expected['initial_node_ids']),
            'native_database_geometry_and_membership_verified': all(components.values()),
            'api_payload_used_to_construct_database_reference': False}


def make_reference(payload, bounds, database):
    comparison = compare_database(payload, bounds, database)
    if not comparison['passed']:
        exc = ValueError('Native API XML differs from complete independent native database expansion')
        exc.native_map_comparison = comparison
        raise exc
    parsed = artifact.parse_xml(payload); expected = canonical_database(database, bounds)
    west, south, east, north = map(Decimal, expected['bounds'])
    inside = {i: {k: n[k] for k in ('lat', 'lon')} for i, n in expected['objects']['node'].items()
              if west <= Decimal(n['lon']) <= east and south <= Decimal(n['lat']) <= north}
    return {'bounds': parsed['bounds'], 'signature': parsed['signature'], 'in_bbox_nodes': inside, 'counts': parsed['counts'],
            'native_database_geometry_verified': True, 'native_database_expansion_verified': True,
            'independent_transport': 'direct_native_database_expansion_then_same_origin_api_then_browser_form',
            'database_reference_version': VERSION}


def capture_reference(site, bounds, directory, name):
    if not isinstance(name, str) or not re.fullmatch('[a-z0-9_-]+', name): raise ValueError('Unsafe native reference label')
    filename = 'osm-expanded-' + name + '.json'; state = site.state / 'frontend'
    program = state / ('osm-expanded-' + name + '.rb')
    program.write_text(rails_reference_program(bounds, filename))
    command = list(site.rails_command)
    command = command[:command.index('server')] + ['runner', '/state/' + program.name]
    site.run(command, 'expanded_native_geometry_' + name, 120)
    value = json.loads((state / filename).read_text())
    atomic_write_json(Path(directory) / (name + '-independent-native-expansion.json'), value)
    canonical_database(value, bounds)
    return value


def save_api_evidence(metadata, payload, bounds, directory, name):
    """Preserve actual native bytes before any oracle comparison can fail."""
    if not isinstance(name, str) or not re.fullmatch('[a-z0-9_-]+', name): raise ValueError('Unsafe native evidence label')
    bounds = artifact.bbox(bounds)
    if not isinstance(payload, bytes) or len(payload) > artifact.MAX_BYTES:
        raise ValueError('Native API payload unavailable or over budget')
    if not isinstance(metadata, dict) or type(metadata.get('http_status')) is not int:
        raise ValueError('Native API status must be explicitly observed')
    permitted = ('http_status', 'content_type', 'content_disposition', 'bytes')
    meta = {k: copy.deepcopy(metadata[k]) for k in permitted if k in metadata}
    if any(not isinstance(meta.get(k, ''), str) or len(meta.get(k, '')) > 2048 for k in ('content_type', 'content_disposition')):
        raise ValueError('Native API headers malformed')
    if meta.get('bytes') != len(payload): raise ValueError('Native API body length differs from observed response')
    directory = Path(directory); path = directory / (name + '-native-api.osm')
    with path.open('xb') as stream: stream.write(payload)
    meta.update(bounds=list(bounds), file=str(path), sha256=hashlib.sha256(payload).hexdigest(),
                preserved_before_validation=True, paid_api_calls=0)
    atomic_write_json(directory / (name + '-native-api-response.json'), meta)
    return meta


def capture_complete_reference(site, bounds, directory, name, *, fetcher):
    """Direct DB oracle first, then a separately captured local API transport."""
    from urllib.parse import urlencode
    database = capture_reference(site, bounds, directory, name)
    metadata, payload = fetcher(site, '/api/0.6/map?' + urlencode({'bbox': ','.join(artifact.bbox(bounds))}))
    metadata = save_api_evidence(metadata, payload, bounds, directory, name)
    if metadata['http_status'] != 200:
        raise ValueError('Native API reference did not return 200; preserved response must be reviewed')
    comparison = compare_database(payload, bounds, database)
    atomic_write_json(Path(directory) / (name + '-native-api-comparison.json'), comparison)
    reference = make_reference(payload, bounds, database)
    return metadata, payload, reference, database
