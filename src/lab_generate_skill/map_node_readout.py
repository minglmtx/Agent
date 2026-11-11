"""Bounded, private native node readback for editor completion evaluation.

Read one PostgreSQL statement snapshot: current objects, tags, version history
and changeset owners agree even if other requests finish during observation.
Never search a geographic baseline by names or scan the full tags/history tables.
This reader grants no task admission and performs no write or browser action.
"""
import json
from .map_node_completion import validate_record

VERSION = 'native-map-node-readback-v1'
MAX_NODES = 64


def integer(value, *, minimum=0):
    if type(value) is not int or not minimum <= value <= 9223372036854775807:
        raise ValueError('Bounded native integer required')
    return str(value)


def capture(site, *, node_ids=None, after_node_id=None):
    """Explicit target(s), or all bounded new IDs after the private baseline.

    An overflow raises instead of silently inspecting just the first 64 nodes.
    IDs are selected independently of actor URLs, stated success, tag content,
    and current account, so wrong values/owners do not disappear from evidence.
    """
    if (node_ids is None) == (after_node_id is None):
        raise ValueError('Choose explicit targets or a post-baseline range')
    if node_ids is not None:
        if not isinstance(node_ids, (list, tuple)) or not 1 <= len(node_ids) <= MAX_NODES:
            raise ValueError('Bounded explicit target list required')
        values = [integer(x, minimum=1) for x in node_ids]
        if len(set(values)) != len(values):
            raise ValueError('Duplicate native target')
        selection = 'SELECT v.id FROM (VALUES ' + ','.join('('+v+'::bigint)' for v in values) + ') v(id)'
    else:
        selection = 'SELECT id FROM current_nodes WHERE id > ' + integer(after_node_id) + ' ORDER BY id LIMIT ' + str(MAX_NODES+1)
    sql = """WITH selected AS (SELECTION), records AS (
 SELECT s.id, json_build_object(
  'current', (SELECT row_to_json(n) FROM current_nodes n WHERE n.id=s.id),
  'tags', (SELECT coalesce(json_agg(t ORDER BY t.k),'[]'::json) FROM current_node_tags t WHERE t.node_id=s.id),
  'history', (SELECT coalesce(json_agg(h ORDER BY h.version),'[]'::json) FROM nodes h WHERE h.node_id=s.id),
  'changeset_owner', (SELECT c.user_id FROM current_nodes n JOIN changesets c ON c.id=n.changeset_id WHERE n.id=s.id)
 ) AS record FROM selected s
 ) SELECT json_build_object(
 'version','native-map-node-readback-v1',
 'max_node_id',(SELECT coalesce(max(id),0) FROM current_nodes),
 'max_changeset_id',(SELECT coalesce(max(id),0) FROM changesets),
 'records',(SELECT coalesce(json_agg(json_build_object('node_id',id,'record',record) ORDER BY id),'[]'::json) FROM records));""".replace('SELECTION', selection)
    result = json.loads(site.app_sql(sql))
    validate_snapshot(result)
    actual = [r['node_id'] for r in result['records']]
    if node_ids is not None and actual != sorted(node_ids):
        raise ValueError('Native target readback incomplete')
    if after_node_id is not None and any(x <= after_node_id for x in actual):
        raise ValueError('Native post-baseline range changed')
    return result


def validate_snapshot(result):
    if not isinstance(result, dict) or set(result) != {'version','max_node_id','max_changeset_id','records'} or result['version'] != VERSION:
        raise ValueError('Complete native snapshot required')
    integer(result['max_node_id']); integer(result['max_changeset_id'])
    rows = result['records']
    if not isinstance(rows, list) or len(rows) > MAX_NODES:
        raise ValueError('Native edit set exceeds bounded readback; no partial scoring')
    ids = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'node_id', 'record'}:
            raise ValueError('Native record binding required')
        integer(row['node_id'], minimum=1); ids.append(row['node_id'])
        current = validate_record(row['record'])
        if current is not None and (current['id'] != row['node_id'] or current['id'] > result['max_node_id'] or current['changeset_id'] > result['max_changeset_id']):
            raise ValueError('Current object disagrees with snapshot binding')
    if ids != sorted(set(ids)):
        raise ValueError('Native records duplicated or unsorted')
    return result
