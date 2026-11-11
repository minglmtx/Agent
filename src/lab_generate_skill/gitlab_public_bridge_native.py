"""Private native evidence for topic filters and exact profile writes.

Candidate only. No browser action, SQL UPDATE, seed injection, external request,
inference or task-specific execution recipe is implemented here.
"""
from copy import deepcopy
import base64
import hashlib
import json
from pathlib import Path
import re
import struct
from urllib.parse import parse_qs, unquote, urlsplit

from .gitlab_read_session import GitlabReadSession
from .gitlab_native_csv_probe import (AUTH_COLUMNS, protected_snapshot,
                                     PROTECTED_TABLES)
from .gitlab_native_read_runtime import full_snapshot
from .gitlab_mutation_native import protection, protection_equal
from .gitlab_persisted_mutation import evaluate as persisted_evaluate
from .gitlab_persisted_goal_runtime import refs_snapshot, validate_refs

VERSION = 'gitlab-public-bridge-native-candidate-v1'
KINDS = {'native_topic_filter', 'native_profile_ssh_key', 'native_profile_name'}
IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False).encode()).hexdigest()


def public_key(value):
    """Only a complete Ed25519 public wire value; never accepts private keys."""
    if not isinstance(value, str) or '\n' in value or '\r' in value:
        raise ValueError('One supplied public Ed25519 key required')
    parts = value.split()
    if len(parts) not in (2, 3) or parts[0] != 'ssh-ed25519':
        raise ValueError('Only supplied public Ed25519 key material is supported')
    try:
        wire = base64.b64decode(parts[1], validate=True)
        length = struct.unpack('>I', wire[:4])[0]
        kind = wire[4:4 + length]
        offset = 4 + length
        key_length = struct.unpack('>I', wire[offset:offset + 4])[0]
        key = wire[offset + 4:]
    except (ValueError, struct.error):
        raise ValueError('Malformed public key wire') from None
    if kind != b'ssh-ed25519' or key_length != 32 or len(key) != 32:
        raise ValueError('Complete native Ed25519 public key wire required')
    return {'key': 'ssh-ed25519 ' + base64.b64encode(wire).decode(),
            'sha256': 'SHA256:' + base64.b64encode(hashlib.sha256(wire).digest()).decode().rstrip('='),
            'md5': ':'.join(re.findall('..', hashlib.md5(wire).hexdigest()))}


def sha256_fingerprint_matches(value, expected):
    """Compare native bytea or OpenSSH display text to the same full digest."""
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    if value.startswith('\\x'):
        if not re.fullmatch(r'\\x[0-9a-fA-F]{64}', value):
            return False
        encoded = base64.b64encode(bytes.fromhex(value[2:])).decode().rstrip('=')
        return expected == 'SHA256:' + encoded
    return value in (expected, expected.removeprefix('SHA256:'))


def rows_index(rows):
    if (not isinstance(rows, list) or any(not isinstance(r, dict)
            or type(r.get('id')) is not int or r['id'] <= 0 for r in rows)):
        raise ValueError('Complete native rows with positive unique primary keys required')
    result = {r['id']: r for r in rows}
    if len(result) != len(rows):
        raise ValueError('Duplicate native primary keys')
    return result


def table_rows(session, site, table):
    """All columns/all rows, bounded ordered traversal in one read-only session."""
    if not IDENTIFIER.fullmatch(table):
        raise ValueError('Generated native table identity required')
    columns = session.select_rows(site, "SELECT column_name,data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='" + table + "' ORDER BY ordinal_position")
    names = [r.get('column_name') for r in columns]
    if not names or 'id' not in names or any(not isinstance(n, str) or not IDENTIFIER.fullmatch(n) for n in names):
        raise ValueError('Complete native id-keyed schema unavailable: ' + table)
    totals = session.select_rows(site, 'SELECT COUNT(*) AS n FROM "' + table + '"')
    if len(totals) != 1 or type(totals[0].get('n')) is not int or totals[0]['n'] < 0:
        raise ValueError('Complete native table count required')
    count = totals[0]['n']; rows = []; cursor = 0
    while len(rows) < count:
        part = session.select_rows(site, 'SELECT row_to_json(t) AS row FROM "' + table + '" t WHERE id>' + str(cursor) + ' ORDER BY id LIMIT 256')
        expected = min(256, count - len(rows))
        if len(part) != expected:
            raise ValueError('Incomplete native table traversal')
        for item in part:
            row = item.get('row')
            if (not isinstance(row, dict) or set(row) != set(names)
                    or type(row.get('id')) is not int or row['id'] <= cursor):
                raise ValueError('Complete ordered native row differs from schema')
            cursor = row['id']; rows.append(row)
    if session.select_rows(site, 'SELECT COUNT(*) AS n FROM "' + table + '"') != totals:
        raise ValueError('Native table changed during traversal')
    rows_index(rows)
    return {'table': table, 'columns': names, 'rows': rows, 'row_count': count,
            'complete': True, 'sha256': digest(rows)}


def validate_table(value, table):
    if (not isinstance(value, dict) or set(value) != {'table', 'columns', 'rows', 'row_count', 'complete', 'sha256'}
            or value['table'] != table or value['complete'] is not True
            or not isinstance(value['columns'], list) or not value['columns']
            or len(set(value['columns'])) != len(value['columns'])
            or 'id' not in value['columns'] or type(value['row_count']) is not int
            or not isinstance(value['rows'], list) or len(value['rows']) != value['row_count']
            or any(not isinstance(r, dict) or set(r) != set(value['columns']) for r in value['rows'])
            or value['sha256'] != digest(value['rows'])):
        raise ValueError('Complete native extra table evidence required')
    rows_index(value['rows'])
    return value


def account_reference(session, site, username):
    if not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', username):
        raise ValueError('Ordinary native benchmark username required')
    rows = session.select_rows(site, "SELECT id,username,admin,external,state FROM users WHERE username='" + username + "'")
    if (len(rows) != 1 or rows[0].get('state') != 'active' or rows[0].get('admin') is not False
            or type(rows[0].get('id')) is not int or rows[0]['id'] <= 0):
        raise ValueError('One active ordinary current account required')
    return rows[0]


def topic_reference(session, site, account, topic, *, evidence_directory):
    """Discover an actual native relation, never substitute text-name search."""
    if not isinstance(topic, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', topic):
        raise ValueError('Explicit native topic name required')
    schemas = session.select_rows(site, "SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public' AND table_name IN ('topics','project_topics','project_topic_links','tags','taggings') ORDER BY table_name,ordinal_position")
    by_table = {}
    for r in schemas:
        by_table.setdefault(r['table_name'], set()).add(r['column_name'])
    model_path = '/opt/gitlab/embedded/service/gitlab-rails/app/models/project.rb'
    model_source = site.command(['cat', model_path], capture_output=True, text=True, timeout=20).stdout
    from gitlab_topic_model_authority import read_authority
    model_authority = read_authority(site, model_source, evidence_directory=evidence_directory)
    relation = model_authority['relation']
    tag_table, link_table, project_column, topic_column, clause = (
        relation[k] for k in ('topic_table', 'link_table', 'project_column', 'topic_column', 'legacy_project_topic_context'))
    required = {'id', project_column, topic_column}
    if clause is not None: required |= {'taggable_type', 'context'}
    if not {'id', 'name'} <= by_table.get(tag_table, set()) or not required <= by_table.get(link_table, set()):
        raise ValueError('Loaded Project topic relation does not match complete actual native schema')
    tags = table_rows(session, site, tag_table); links = table_rows(session, site, link_table)
    matches = [r for r in tags['rows'] if r.get('name') == topic]
    if len(matches) != 1:
        raise ValueError('Requested topic absent or ambiguous in native seed')
    ident = matches[0]['id']; project_ids = []
    for row in links['rows']:
        if row.get(topic_column) != ident:
            continue
        if clause and (row.get('taggable_type') != 'Project' or row.get('context') != clause):
            continue
        project_ids.append(row.get(project_column))
    if any(type(i) is not int or i <= 0 for i in project_ids) or len(set(project_ids)) != len(project_ids):
        raise ValueError('Complete unambiguous native topic project relation required')
    user_id = account['id']
    allowed = session.select_rows(site, "SELECT p.id,r.path,p.name,p.archived FROM projects p JOIN routes r ON r.source_id=p.id AND r.source_type='Project' WHERE p.pending_delete=false AND p.marked_for_deletion_at IS NULL AND p.archived=false AND (p.visibility_level=20 OR (p.visibility_level=10 AND " + ('false' if account['external'] else 'true') + ") OR EXISTS (SELECT 1 FROM project_authorizations a WHERE a.project_id=p.id AND a.user_id=" + str(user_id) + ")) ORDER BY p.id")
    members = [r for r in allowed if r['id'] in set(project_ids)]
    if not members:
        raise ValueError('Requested native topic has no account-accessible members')
    return {'topic': topic, 'account_id': user_id, 'projects': members,
            'accessible_non_archived_projects': allowed,
            'topic_table': tags, 'link_table': links,
            'relation': {'topic_table': tag_table, 'link_table': link_table,
                         'topic_column': topic_column, 'project_column': project_column,
                         'legacy_project_topic_context': clause,
                         'native_project_model_sha256': hashlib.sha256(model_source.encode()).hexdigest() if model_source is not None else None,
                         'native_model_authority': model_authority}}


def validate_topic_state(value, topic, account_id):
    if (not isinstance(value, dict) or value.get('topic') != topic
            or value.get('account_id') != account_id or not isinstance(value.get('relation'), dict)):
        raise ValueError('Actual requested native topic/account reference required')
    relation = value['relation']
    if relation.get('topic_table') not in ('topics', 'tags') or relation.get('link_table') not in ('project_topics', 'project_topic_links', 'taggings'):
        raise ValueError('Discovered supported native topic relation required')
    tags = validate_table(value['topic_table'], relation['topic_table'])
    links = validate_table(value['link_table'], relation['link_table'])
    matches = [r for r in tags['rows'] if r.get('name') == topic]
    if len(matches) != 1:
        raise ValueError('Unique complete native topic definition required')
    project_column, topic_column = relation.get('project_column'), relation.get('topic_column')
    if project_column not in links['columns'] or topic_column not in links['columns']:
        raise ValueError('Native relation schema does not cover configured identities')
    context = relation.get('legacy_project_topic_context')
    if not re.fullmatch('[0-9a-f]{64}', relation.get('native_project_model_sha256') or ''):
        raise ValueError('Topic relation needs actual native model source authority')
    from gitlab_topic_model_authority import verify_authority
    verify_authority(relation.get('native_model_authority'),
                     {k: relation[k] for k in ('topic_table', 'link_table', 'project_column', 'topic_column', 'legacy_project_topic_context')},
                     relation['native_project_model_sha256'])
    related = {r[project_column] for r in links['rows'] if r[topic_column] == matches[0]['id']
               and (context is None or r.get('taggable_type') == 'Project' and r.get('context') == context)}
    accessible = value.get('accessible_non_archived_projects')
    if (not isinstance(accessible, list) or not accessible
            or any(set(r) != {'id', 'path', 'name', 'archived'} or type(r['id']) is not int
                   or r['id'] <= 0 or r['archived'] is not False or not isinstance(r['path'], str)
                   or not r['path'] or not isinstance(r['name'], str) for r in accessible)):
        raise ValueError('Complete independently account-accessible native project pool required')
    rows_index(accessible)
    if len({r['path'] for r in accessible}) != len(accessible):
        raise ValueError('Duplicate native accessible project route')
    members = [r for r in accessible if r['id'] in related]
    if not members or members != value.get('projects'):
        raise ValueError('Native topic membership differs from complete actual relation/access reference')
    return value


def _full_guard(site, account_id, progress):
    with GitlabReadSession(site) as session:
        def reader(current, sql):
            expression = 'row_to_json(t)::text'
            if 'md5(' + expression + ')' in sql and ' FROM "users" t' in sql:
                subtract = ''.join("-'" + field + "'" for field in AUTH_COLUMNS)
                sql = sql.replace(expression, '(CASE WHEN t.id=' + str(account_id) + ' THEN to_jsonb(t)' + subtract + ' ELSE to_jsonb(t) END)::text')
            return session.select_rows(current, sql)
        return full_snapshot(protected_snapshot(site, progress, reader=reader))


def collect(site, contract, username, progress):
    """No mutating initialization: source reset belongs to the ordinary factory."""
    kind = contract['gitlab_public_bridge']['kind']; params = contract['public_parameters']
    if kind not in KINDS:
        raise ValueError('Supported common bridge kind required')
    with GitlabReadSession(site) as session:
        account = account_reference(session, site, username)
        if kind == 'native_topic_filter':
            state = topic_reference(session, site, account, params['topic'],
                                    evidence_directory=Path(progress).parent / (Path(progress).name + '-topic-authority'))
        else:
            state = {'users': table_rows(session, site, 'users')}
            if kind == 'native_profile_ssh_key':
                state['keys'] = table_rows(session, site, 'keys')
                if not {'user_id', 'key', 'title'} <= set(state['keys']['columns']):
                    raise ValueError('Actual native complete SSH-key schema unavailable')
    if kind == 'native_profile_name':
        spec = {'kind': 'profile_name', 'identity': account['id'], 'value': params['name']}
        guard = protection(site, spec, account['id'], progress)
        full_snapshot({k: v for k, v in guard.items() if k != 'profile_relations'})
    else:
        guard = _full_guard(site, account['id'], progress)
    return {'version': VERSION, 'kind': kind, 'account': account, 'state': state,
            'guard': guard, 'refs': refs_snapshot(site)}


def _same_other_users(old, new, account_id, *, permit_name):
    validate_table(old, 'users'); validate_table(new, 'users')
    if old['columns'] != new['columns']:
        return False
    before, after = rows_index(old['rows']), rows_index(new['rows'])
    if set(before) != set(after) or account_id not in before:
        return False
    ignored = set(AUTH_COLUMNS) | ({'name'} if permit_name else set())
    for ident, row in before.items():
        fields = ignored if ident == account_id else set()
        if {k: v for k, v in row.items() if k not in fields} != {k: v for k, v in after[ident].items() if k not in fields}:
            return False
    return True


def integrity(contract, old, new):
    kind = contract['gitlab_public_bridge']['kind']; params = contract['public_parameters']
    if (old.get('version') != VERSION or new.get('version') != VERSION
            or old.get('kind') != kind or new.get('kind') != kind or old['account'] != new['account']):
        return False
    validate_refs(old['refs']); validate_refs(new['refs'])
    if old['refs'] != new['refs']:
        return False
    account_id = old['account']['id']
    if kind == 'native_topic_filter':
        full_snapshot(old['guard']); full_snapshot(new['guard'])
        validate_topic_state(old['state'], params['topic'], account_id)
        validate_topic_state(new['state'], params['topic'], account_id)
        return old['guard'] == new['guard'] and old['state'] == new['state']
    if not _same_other_users(old['state']['users'], new['state']['users'], account_id,
                             permit_name=kind == 'native_profile_name'):
        return False
    if kind == 'native_profile_name':
        spec = {'kind': 'profile_name', 'identity': account_id, 'value': params['name']}
        for value in (old, new):
            full_snapshot({k: v for k, v in value['guard'].items() if k != 'profile_relations'})
        return old['guard'] == new['guard'] or protection_equal(old['guard'], new['guard'], spec, account_id)
    full_snapshot(old['guard']); full_snapshot(new['guard'])
    if old['guard'] != new['guard']:
        return False
    a, b = old['state']['keys'], new['state']['keys']
    validate_table(a, 'keys'); validate_table(b, 'keys')
    if a['columns'] != b['columns']:
        return False
    before, after = rows_index(a['rows']), rows_index(b['rows'])
    return set(before) <= set(after) and all(after[i] == row for i, row in before.items()) and len(after) - len(before) <= 1


def _healthy(capture, origin):
    if not isinstance(capture, dict) or not isinstance(capture.get('url'), str):
        raise ValueError('Actual native terminal page capture required')
    u, expected = urlsplit(capture['url']), urlsplit(origin)
    if (u.scheme, u.netloc) != (expected.scheme, expected.netloc):
        return False
    if type(capture.get('http_status')) is not int:
        raise ValueError('Actual native terminal HTTP status evidence missing')
    return (type(capture.get('http_status')) is int and 200 <= capture['http_status'] < 300
            and capture.get('login_page') is False and capture.get('error_page') is False)


def topic_checks(contract, initial, captures, terminal, origin):
    expected = initial['state']; topic = contract['public_parameters']['topic']
    if not isinstance(captures, list) or not captures:
        raise ValueError('Actual normal captured native collection pages required')
    valid_pages = []
    for state in captures:
        if not _healthy(state, origin) or not state.get('native_topic_control'):
            continue
        u = urlsplit(state['url']); query = parse_qs(u.query, keep_blank_values=True)
        field = state.get('topic_field')
        if not isinstance(field, str) or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', field):
            continue
        # The key is taken from the actual selected native control/captured
        # successful GET, never a URL manufactured by this module.
        if (u.path.rstrip('/') not in ('/explore', '/explore/projects')
                or state.get('account_id') != initial['account']['id']
                or state.get('topic_value') != topic or query.get(field) != [topic]
                or state.get('document_get_200') is not True
                or state.get('issued_ax_contains_control') is not True
                or state.get('native_control_query_agrees') is not True):
            continue
        if query.get('non_archived', ['true']) != ['true'] or query.get('name', ['']) != ['']:
            continue
        if any(values != [''] for key, values in query.items()
               if key not in (field, 'sort', 'page', 'non_archived')):
            continue
        number = state.get('page_number'); pages = state.get('pagination_pages'); paths = state.get('project_paths')
        if (type(number) is not int or number < 1 or not isinstance(pages, list)
                or not pages or any(type(i) is not int or i < 1 for i in pages)
                or len(set(pages)) != len(pages) or number not in pages
                or not isinstance(paths, list) or len(set(paths)) != len(paths)
                or any(not isinstance(p, str) or not p or p.startswith('/') for p in paths)):
            raise ValueError('Complete actual native topic page capture malformed')
        valid_pages.append(state)
    current = next((s for s in reversed(valid_pages) if s['url'] == terminal['url']), None)
    expected_paths = {r['path'] for r in expected['projects']}
    chosen = {}
    if current is not None:
        for state in valid_pages:
            if state['pagination_pages'] == current['pagination_pages']:
                chosen[state['page_number']] = state
    shown = [p for state in chosen.values() for p in state['project_paths']]
    return {'native_topic_filter_applied': current is not None,
            'complete_native_pagination_observed': current is not None and set(chosen) == set(current['pagination_pages']),
            'exact_native_topic_members_displayed': len(shown) == len(set(shown)) and set(shown) == expected_paths}


def evaluate(contract, initial, final, captures, terminal, *, site_origin, runtime_error=None):
    def unknown(reason):
        return {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': {}, 'reason': reason}
    if runtime_error:
        return unknown('Native execution or complete state capture failed')
    try:
        kind = contract['gitlab_public_bridge']['kind']; params = contract['public_parameters']
        preserved = integrity(contract, initial, final)
        checks = {'complete_unrelated_native_state_preserved': preserved,
                  'valid_local_terminal_page': _healthy(terminal, site_origin)}
        if kind == 'native_topic_filter':
            checks.update(topic_checks(contract, initial, captures, terminal, site_origin))
        elif kind == 'native_profile_name':
            ident = initial['account']['id']
            before = rows_index(initial['state']['users']['rows']); after = rows_index(final['state']['users']['rows'])
            if before[ident]['name'] == params['name']:
                return unknown('Requested profile name already holds at initialization')
            result = persisted_evaluate({'kind': 'profile_name', 'identity': ident, 'value': params['name']},
                {'identity': ident, 'rows': [{'id': r['id'], 'username': r['username'], 'name': r['name']} for r in before.values()]},
                {'identity': ident, 'rows': [{'id': r['id'], 'username': r['username'], 'name': r['name']} for r in after.values()]},
                protected_state_unchanged=preserved)
            if result['status'] == 'unknown':
                return unknown(result['reason'])
            checks.update(result['checks'])
            checks['current_account_profile_capture'] = terminal.get('account_id') == ident
        elif kind == 'native_profile_ssh_key':
            key = public_key(params['public_key']); account = initial['account']['id']
            before = rows_index(initial['state']['keys']['rows']); after = rows_index(final['state']['keys']['rows'])
            if any(r.get('user_id') == account and public_key(r['key'])['key'] == key['key'] for r in before.values() if isinstance(r.get('key'), str) and r['key'].startswith('ssh-ed25519 ')):
                return unknown('Supplied public key is already saved at initialization')
            inserted = [r for ident, r in after.items() if ident not in before]
            target = inserted[0] if len(inserted) == 1 else None
            same_key = target is not None and public_key(target.get('key'))['key'] == key['key']
            fingerprint = target.get('fingerprint_sha256') if target is not None else None
            fingerprint_ok = sha256_fingerprint_matches(fingerprint, key['sha256'])
            md5_fingerprint = target.get('fingerprint') if target is not None else None
            fingerprint_ok = fingerprint_ok and (md5_fingerprint is None or md5_fingerprint in (key['md5'], key['md5'].replace(':', '')))
            checks.update(exactly_one_native_key_saved=len(inserted) == 1,
                          supplied_key_and_title_saved=same_key and target.get('title') == params['title'],
                          key_belongs_to_current_account=target is not None and target.get('user_id') == account,
                          native_fingerprint_agrees=fingerprint_ok,
                          current_account_profile_capture=terminal.get('account_id') == account)
        else:
            raise ValueError('Unsupported bridge kind')
    except (KeyError, TypeError, ValueError):
        return unknown('Complete native bridge evidence is missing or inconsistent')
    passed = all(v is True for v in checks.values())
    return {'version': VERSION, 'status': 'success' if passed else 'failure',
            'reward': float(passed), 'checks': checks, 'reason': None}


def feedback(result):
    """Names/pass status only; no private IDs, references, expected rows or route."""
    return {'status': result['status'], 'reward': result['reward'],
            'reason': result.get('reason'),
            'checks': [{'condition': k, 'passed': v} for k, v in result['checks'].items()],
            'reference_values_provided': False, 'action_sequence_provided': False}
