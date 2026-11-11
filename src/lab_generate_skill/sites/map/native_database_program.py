"""Original full native Rails selection, with exclusive complete private output.

The query/expansion/cap semantics match the selected frozen capsule. Only output
materialization changes: no overwrite, declared byte budget, fsync and close.
No response/XML input or modification of the installed HTTP node cap.
"""

import json
import re
from .native_bounds import request_bounds
from .native_database import DATABASE_VERSION

SELECTION = """ActiveRecord::Base.connection.execute("SET default_transaction_read_only=on")
bounds = BoundingBox.from_s(BOUNDS)
bounds.check_boundaries
bounds.check_size
nodes = Node.bbox(bounds).where(:visible => true).includes(:node_tags).limit(500001).to_a
initial_node_ids = nodes.map(&:id)
raise "Complete private reference inspection budget exceeded" if initial_node_ids.length > 500000
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
raise "Expanded native object budget exceeded" if nodes.length + ways.length + relations.length > 500000
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
"""

OUTPUT = """serialized = JSON.generate(payload)
raise "Complete native reference byte budget exceeded" if serialized.bytesize > BYTE_BUDGET
File.open(OUTPUT_PATH, File::WRONLY | File::CREAT | File::EXCL, 0600) do |file|
  written = file.write(serialized)
  raise "Incomplete native reference write" unless written == serialized.bytesize
  file.flush
  file.chmod(0400)
  file.fsync
end
File.open(OUTPUT_DIRECTORY, File::RDONLY) { |directory| directory.fsync }
"""


def reference_program(bounds: object, label: str, max_output_bytes: int) -> bytes:
    bounds = request_bounds(bounds)
    if type(label) is not str or re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", label) is None:
        raise ValueError("Bounded original native reference label required")
    if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= 2 * 1024**4:
        raise ValueError("Explicit complete native output byte budget required")
    directory = "/state/native-reference-" + label
    selection = SELECTION.replace("BOUNDS", json.dumps(",".join(bounds))).replace(
        "VERSION_VALUE", json.dumps(DATABASE_VERSION)
    )
    materialization = (
        OUTPUT.replace("BYTE_BUDGET", str(max_output_bytes))
        .replace(
            "OUTPUT_PATH", json.dumps(directory + "/osm-expanded-" + label + ".json")
        )
        .replace("OUTPUT_DIRECTORY", json.dumps(directory))
    )
    return (selection + materialization).encode()
