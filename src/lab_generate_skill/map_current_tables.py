"""Bounded exact comparisons for the native OSM history/current projection.

No sampling or probabilistic hash is used for equality. A valid unique target
key plus equal row counts and a full key join also detects duplicate source
keys. Ranges cover the union of source and target keys, including extra rows.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Projection:
    target: str
    source: str
    columns: tuple
    target_columns: tuple
    keys: tuple


def _projection(target, source, columns, keys, entity=False):
    columns = tuple(columns.split(','))
    targets = ('id',) + columns[1:] if entity else columns
    return Projection(target, source, columns, targets, tuple(keys.split(',')))


PROJECTIONS = {p.target: p for p in (
    _projection('current_nodes', 'nodes', 'node_id,latitude,longitude,changeset_id,visible,timestamp,tile,version', 'node_id', True),
    _projection('current_node_tags', 'node_tags', 'node_id,k,v', 'node_id,k'),
    _projection('current_ways', 'ways', 'way_id,changeset_id,timestamp,visible,version', 'way_id', True),
    _projection('current_way_tags', 'way_tags', 'way_id,k,v', 'way_id,k'),
    _projection('current_way_nodes', 'way_nodes', 'way_id,node_id,sequence_id', 'way_id,sequence_id'),
    _projection('current_relations', 'relations', 'relation_id,changeset_id,timestamp,visible,version', 'relation_id', True),
    _projection('current_relation_tags', 'relation_tags', 'relation_id,k,v', 'relation_id,k'),
    _projection('current_relation_members', 'relation_members', 'relation_id,member_id,member_role,member_type,sequence_id', 'relation_id,member_type,member_id,member_role,sequence_id'),
)}


def projection(name):
    if name not in PROJECTIONS:
        raise ValueError('Only declared native OSM projections are allowed')
    return PROJECTIONS[name]


def bounds(lower, upper):
    if type(lower) is not int or type(upper) is not int or not 0 <= lower < upper <= 2**63 - 1:
        raise ValueError('A nonempty bounded native ID interval is required')
    return f'>={lower} AND {{column}}<{upper}'


def select_range(p, source, lower, upper):
    bounds(lower, upper)
    cols = p.columns if source else p.target_columns
    table = p.source if source else p.target
    selected = ','.join(f'{col} AS {alias}' for col, alias in zip(cols, p.columns))
    return f'SELECT {selected} FROM {table} WHERE {cols[0]}>={lower} AND {cols[0]}<{upper}'


def comparison_sql(name, lower, upper):
    p = projection(name)
    src, dst = select_range(p, True, lower, upper), select_range(p, False, lower, upper)
    on = ' AND '.join(f's.{k}=t.{k}' for k in p.keys)
    sc = ','.join('s.' + c for c in p.columns)
    tc = ','.join('t.' + c for c in p.columns)
    key = p.keys[0]
    return ("SELECT json_build_object('source_rows',(SELECT count(*) FROM (" + src + ") a),"
            "'target_rows',(SELECT count(*) FROM (" + dst + ") b),'mismatch',EXISTS("
            'SELECT 1 FROM (' + src + ') s FULL OUTER JOIN (' + dst + ') t ON ' + on +
            f' WHERE s.{key} IS NULL OR t.{key} IS NULL OR '
            f'ROW({sc}) IS DISTINCT FROM ROW({tc})));')


def require_equal(result):
    if (not isinstance(result, dict) or set(result) != {'source_rows', 'target_rows', 'mismatch'}
            or type(result['source_rows']) is not int or type(result['target_rows']) is not int
            or min(result['source_rows'], result['target_rows']) < 0
            or type(result['mismatch']) is not bool):
        raise ValueError('Actual exact comparison result required')
    if result['mismatch'] or result['source_rows'] != result['target_rows']:
        raise ValueError('Native current projection differs from history')
    return result['source_rows']


def next_key_sql(name, lower):
    p = projection(name)
    if type(lower) is not int or not 0 <= lower <= 2**63 - 1:
        raise ValueError('Bounded native cursor required')
    # A target key above the next source key cannot change the union minimum.
    # Bound the target probe to avoid walking a large empty/dead-index gap
    # toward another worker's distant range. If source is exhausted, still
    # inspect the entire remaining target tail to detect extraneous rows.
    return (f'SELECT min(key) FROM (WITH source_next AS ('
            f'SELECT min({p.columns[0]}) AS key FROM {p.source} '
            f'WHERE {p.columns[0]}>={lower}) '
            f'SELECT key FROM source_next UNION ALL '
            f'SELECT min({p.target_columns[0]}) FROM {p.target} '
            f'WHERE {p.target_columns[0]}>={lower} AND '
            f'{p.target_columns[0]}<=COALESCE((SELECT key FROM source_next),'
            f'9223372036854775807)) available;')



def insert_sql(name, lower, upper):
    p = projection(name); bounds(lower, upper)
    return (f'INSERT INTO {p.target} ({",".join(p.target_columns)}) SELECT '
            f'{",".join(p.columns)} FROM {p.source} WHERE '
            f'{p.columns[0]}>={lower} AND {p.columns[0]}<{upper};')


def insert_missing_sql(name, lower, upper):
    p = projection(name); bounds(lower, upper)
    mapping = dict(zip(p.columns, p.target_columns))
    match = ' AND '.join(f't.{mapping[k]}=s.{k}' for k in p.keys)
    return (f'INSERT INTO {p.target} ({",".join(p.target_columns)}) SELECT '
            + ','.join('s.' + c for c in p.columns) + f' FROM {p.source} s WHERE '
            f's.{p.columns[0]}>={lower} AND s.{p.columns[0]}<{upper} AND NOT EXISTS '
            f'(SELECT 1 FROM {p.target} t WHERE {match});')


def require_target_key(name, native_key):
    p = projection(name)
    mapped = dict(zip(p.columns, p.target_columns))
    expected = [mapped[k] for k in p.keys]
    if (native_key.get('columns') != expected or native_key.get('primary') is not True
            or native_key.get('valid') is not True or native_key.get('ready') is not True):
        raise ValueError('Actual valid unique target primary key is required')
    return True
