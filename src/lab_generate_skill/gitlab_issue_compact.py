"""Compact private issue snapshots, preserving all previously checked fields.

SHA256 each ordered JSON record, then SHA256 the ordered fixed-length hashes.
Native PostgreSQL row_to_json and legacy Python conversion use the same field
order and compact UTF-8 JSON. The online baseline must match before inference.
"""
import hashlib
import json
import re

COLUMNS = ('id', 'iid', 'project_id', 'author_id', 'title', 'description', 'state_id', 'confidential')
ENCODING = 'sha256-v2'


def ranges(ids):
    if any(type(i) is not int or i <= 0 for i in ids) or ids != sorted(set(ids)):
        raise ValueError('Issue IDs must be distinct sorted positive integers')
    result = []
    for i in ids:
        if result and i == result[-1][1] + 1: result[-1][1] = i
        else: result.append([i, i])
    return result


def predicate(value):
    previous = 0; terms = []
    if not isinstance(value, list): raise ValueError('Missing baseline ID ranges')
    for item in value:
        if not isinstance(item, list) or len(item) != 2: raise ValueError('Malformed baseline ID range')
        lo, hi = item
        if type(lo) is not int or type(hi) is not int or not previous < lo <= hi:
            raise ValueError('Invalid baseline ID range')
        terms.append(f'id BETWEEN {lo} AND {hi}'); previous = hi
    return '(' + ' OR '.join(terms) + ')' if terms else 'false'


def digest_records(rows):
    h = hashlib.sha256()
    for row in sorted(rows, key=lambda r: r['id']):
        encoded = json.dumps({k: row[k] for k in COLUMNS}, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        h.update(hashlib.sha256(encoded).hexdigest().encode('ascii'))
    return {'count': len(rows), 'sha256': h.hexdigest()}


def compact_legacy(state, baseline=None):
    original = state if baseline is None else baseline
    ids = sorted(r['id'] for r in original['issues']); known = set(ids)
    return {'encoding': ENCODING, 'user': state['user'], 'projects': state['projects'],
            'known_id_ranges': ranges(ids),
            'protected_issues': digest_records([r for r in state['issues'] if r['id'] in known]),
            'added_issues': [r for r in state['issues'] if r['id'] not in known]}


def validate(state, *, initial=False):
    if not isinstance(state, dict) or state.get('encoding') != ENCODING:
        raise ValueError('Missing compact issue state')
    predicate(state.get('known_id_ranges'))
    d = state.get('protected_issues', {})
    if type(d.get('count')) is not int or d['count'] < 0 or not re.fullmatch('[a-f0-9]{64}', str(d.get('sha256', ''))):
        raise ValueError('Missing protected issue digest')
    if not isinstance(state.get('added_issues'), list): raise ValueError('Missing added issue records')
    added = state['added_issues']
    if any(not isinstance(r, dict) or set(r) != set(COLUMNS) or type(r['id']) is not int for r in added):
        raise ValueError('Malformed added issue record')
    if len({r['id'] for r in added}) != len(added) or any(
        lo <= r['id'] <= hi for r in added for lo, hi in state['known_id_ranges']
    ): raise ValueError('Added issues overlap the baseline or contain duplicates')
    if initial and (added or d['count'] != sum(hi-lo+1 for lo,hi in state['known_id_ranges'])):
        raise ValueError('Dirty or incomplete compact baseline')


def read(site, username, *, baseline, select):
    name = "'" + username.replace("'", "''") + "'"
    users = select(site, 'SELECT id,username FROM users WHERE username=' + name)
    if len(users) != 1: raise ValueError('Missing or ambiguous issue author')
    if baseline is None:
        ids = select(site, 'SELECT array_agg(id ORDER BY id) AS ids FROM issues')[0]['ids'] or []
        known = ranges(ids)
    else:
        validate(baseline, initial=True); known = baseline['known_id_ranges']
    condition = predicate(known)
    columns = ','.join(COLUMNS)
    query = ("SELECT count(*) AS count,encode(sha256(convert_to(COALESCE(string_agg("
             "encode(sha256(convert_to(row_to_json(r)::text,'UTF8')),'hex'),'' ORDER BY id),''),'UTF8')),'hex') AS sha256 "
             f"FROM (SELECT {columns} FROM issues WHERE {condition}) r")
    state = {'encoding': ENCODING, 'user': users[0],
             'projects': select(site, "SELECT p.id,p.name,r.path FROM projects p JOIN routes r ON r.source_id=p.id AND r.source_type='Project' ORDER BY p.id"),
             'known_id_ranges': known, 'protected_issues': select(site, query)[0],
             'added_issues': select(site, f'SELECT {columns} FROM issues WHERE NOT {condition} ORDER BY id')}
    validate(state, initial=baseline is None)
    return state
