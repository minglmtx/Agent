"""Native callback port; source controls and scoring preserved."""
from collections import Counter

import hashlib

import json

from pathlib import Path

import re

import uuid

from lab_generate_skill.gitlab_native_csv_probe import (PROTECTED_TABLES, protected_snapshot,
    native_command, normalize_reference)

from lab_generate_skill.gitlab_read_session import GitlabReadSession

from lab_generate_skill.gitlab_native_read_runtime import full_snapshot

from lab_generate_skill.gitlab_persisted_goal_runtime import validate_refs, target_repository

from lab_generate_skill.site_database import select_rows

from lab_generate_skill.io_utils import atomic_write_json

from . import gitlab_remaining_components as component

def capture_full_rows(site, progress):
    """Same installed full16 algorithm plus complete native keyed row MD5s."""
    records = {t: [] for t in PROTECTED_TABLES}; keys = {}
    with GitlabReadSession(site) as session:
        def reader(current, sql):
            if 'FROM pg_index ' in sql:
                rows = session.select_rows(current, sql)
                m = re.search(r"c\.oid='public\.([a-z_]+)'::regclass", sql)
                if m and len(rows) == 1: keys[m.group(1)] = rows[0]['names']
                return rows
            m = re.search(r'FROM "([a-z_]+)" t', sql)
            table = m.group(1) if m else None
            if table and 'md5(row_to_json(t)::text) AS digest' in sql:
                order = ','.join('"' + k + '"' for k in keys[table])
                sql = sql.replace('md5(row_to_json(t)::text) AS digest',
                    'md5(row_to_json(t)::text) AS digest,json_build_array(' + order + ') AS proof_key')
                rows = session.select_rows(current, sql)
                records[table].extend({'key': r['proof_key'], 'digest': r['digest']} for r in rows)
                return rows
            return session.select_rows(current, sql)
        full = protected_snapshot(site, progress, reader=reader)
    validate_full_rows(full, records)
    return {'full': full, 'row_digests': records}

def validate_full_rows(full, records):
    full_snapshot(full)
    if not isinstance(records, dict) or set(records) != set(PROTECTED_TABLES):
        raise ValueError('Every complete sixteen-table row digest list required')
    for table, rows in records.items():
        if not isinstance(rows, list) or len(rows) != full[table]['rows']:
            raise ValueError('Native full row count differs: ' + table)
        seen = set(); hasher = hashlib.sha256()
        for row in rows:
            if (not isinstance(row, dict) or set(row) != {'key', 'digest'}
                or not isinstance(row['key'], list) or len(row['key']) != len(full[table]['key'])
                or any(type(x) not in (int, str) for x in row['key'])
                or not re.fullmatch('[0-9a-f]{32}', row['digest'])):
                raise ValueError('Native unique key / complete row fingerprint unavailable')
            k = tuple(row['key'])
            if k in seen: raise ValueError('Duplicate native row key')
            seen.add(k); hasher.update((row['digest'] + '\n').encode())
        if hasher.hexdigest() != full[table]['sha256']:
            raise ValueError('Full native digest cannot be reconstructed from all rows: ' + table)
    return True

def template_baseline(site, username):
    from lab_generate_skill.gitlab_project_creation import project_state
    state = project_state(site, username)
    user = state['user']
    names = select_rows(site, "SELECT id,name,path,type,owner_id,parent_id FROM namespaces WHERE type='User' AND owner_id=" + str(user['id']))
    if len(names) != 1 or names[0]['path'] != username:
        raise component.PendingCapability('Unique actual native user namespace unavailable')
    return {'project_state': state, 'user_namespace': names[0],
        'namespace_ids': [r['id'] for r in select_rows(site, 'SELECT id FROM namespaces ORDER BY id')],
        'route_ids': [r['id'] for r in select_rows(site, 'SELECT id FROM routes ORDER BY id')],
        'member_ids': [r['id'] for r in select_rows(site, 'SELECT id FROM members ORDER BY id')]}

def authorized_creation(site, c, initial, final):
    """Qualify exact bound new rows; wrong name remains a predicate failure."""
    old = {r['id'] for r in initial['project_state']['projects']}
    created = [r for r in final['projects'] if r['id'] not in old]
    if not created: return {'created_project': None, 'excluded_row_keys': {}, 'rows': {}}
    if len(created) != 1: raise component.PendingCapability('Unexpected number of newly created projects')
    p = created[0]; params = c['public_parameters']; account = initial['project_state']['user']['id']
    expected_path = params['namespace'] + '/' + params['project_path']
    if (p['creator_id'] != account or p['path'] != params['project_path'] or p['full_path'] != expected_path
        or p['visibility_level'] != 0 or p['namespace_id'] != initial['user_namespace']['id']):
        raise component.PendingCapability('Creation outside the exact declared native project/account/path/visibility')
    # Project.namespace_id is the existing parent User/Group namespace.
    # Project.project_namespace_id is the distinct new Project namespace.
    n = select_rows(site, 'SELECT n.id,n.name,n.path,n.type,n.owner_id,n.parent_id FROM namespaces n '
        'JOIN projects p ON p.project_namespace_id=n.id WHERE p.id=' + str(p['id']))
    if (len(n) != 1 or n[0]['id'] in initial['namespace_ids'] or n[0]['type'] != 'Project'
        or n[0]['parent_id'] != initial['user_namespace']['id'] or n[0]['path'] != p['path']):
        raise component.PendingCapability('Exact new native project namespace effect unavailable')
    routes = select_rows(site, 'SELECT id,source_id,source_type,path FROM routes WHERE source_id IN ('
        + str(p['id']) + ',' + str(n[0]['id']) + ') ORDER BY id')
    new_routes = [r for r in routes if r['id'] not in initial['route_ids']]
    if (not new_routes or any(r['path'] != expected_path or (r['source_type'], r['source_id'])
        not in (('Project', p['id']), ('Namespace', n[0]['id'])) for r in new_routes)
        or sum(r['source_type'] == 'Project' for r in new_routes) != 1):
        raise component.PendingCapability('Exact new native project route effect unavailable')
    authorizations = select_rows(site, 'SELECT user_id,project_id,access_level FROM project_authorizations WHERE project_id=' + str(p['id']) + ' ORDER BY user_id')
    if authorizations != [{'user_id': account, 'project_id': p['id'], 'access_level': 50}]:
        raise component.PendingCapability('Exact single-account native project authorization unavailable')
    members = select_rows(site, "SELECT id,source_id,source_type,user_id,access_level,type FROM members WHERE source_type='Project' AND source_id=" + str(p['id']) + ' ORDER BY id')
    if (len(members) > 1 or any(r['id'] in initial['member_ids'] or r['user_id'] != account
        or r['access_level'] != 50 or r['type'] != 'ProjectMember' for r in members)):
        raise component.PendingCapability('Exact project owner membership effect unavailable')
    return {'created_project': p, 'excluded_row_keys': {
        'projects': [{'id': p['id']}], 'namespaces': [{'id': n[0]['id']}],
        'routes': [{'id': r['id']} for r in new_routes],
        'project_authorizations': [{'user_id': account, 'project_id': p['id'], 'access_level': 50}],
        'members': [{'id': r['id']} for r in members]},
        'rows': {'namespace': n[0], 'routes': new_routes, 'authorizations': authorizations, 'members': members}}

def creation_guard(before, after, effects):
    validate_full_rows(before['full'], before['row_digests']); validate_full_rows(after['full'], after['row_digests'])
    excluded = effects['excluded_row_keys']; reduced = {}
    if set(excluded) - {'projects', 'namespaces', 'routes', 'project_authorizations', 'members'}:
        raise ValueError('No unrelated table may be relaxed')
    for table, rows in after['row_digests'].items():
        a, b = before['full'][table], after['full'][table]
        if (a['columns'], a['key']) != (b['columns'], b['key']): return False
        targets = excluded.get(table, []); keys = []
        for target in targets:
            if set(target) != set(b['key']): raise ValueError('Exact complete native unique key required for new-row reduction')
            keys.append(tuple(target[k] for k in b['key']))
        if len(set(keys)) != len(keys): raise ValueError('Duplicate authorized row key')
        old_keys = {tuple(r['key']) for r in before['row_digests'][table]}
        if old_keys & set(keys): return False
        remaining = [r for r in rows if tuple(r['key']) not in set(keys)]
        if len(rows) - len(remaining) != len(keys): return False
        reduced[table] = remaining
    # Compare every existing row's complete MD5, its native traversal position,
    # and every full schema/key. A passed mask flag cannot substitute for this.
    return reduced == before['row_digests']

def verify_creation_effects(c, initial, final, effects):
    """Recompute exact new-row authorization from complete original raw rows."""
    component.validate_state(initial['project_state']); component.validate_state(final)
    old = {p['id'] for p in initial['project_state']['projects']}
    created = [p for p in final['projects'] if p['id'] not in old]
    if not created:
        if effects != {'created_project': None, 'excluded_row_keys': {}, 'rows': {}}:
            raise ValueError('No native project may invent authorized side effects')
        return True
    if len(created) != 1 or effects.get('created_project') != created[0]:
        raise ValueError('Exactly one actual native created project required')
    p = created[0]; params = c['public_parameters']; account = initial['project_state']['user']['id']
    path = params['namespace'] + '/' + params['project_path']; rows = effects['rows']
    n, routes, auth, members = rows['namespace'], rows['routes'], rows['authorizations'], rows['members']
    if (p['creator_id'] != account or p['path'] != params['project_path'] or p['full_path'] != path
        or p['visibility_level'] != 0 or p['namespace_id'] != initial['user_namespace']['id']
        or n['id'] in initial['namespace_ids']
        or n['type'] != 'Project' or n['parent_id'] != initial['user_namespace']['id'] or n['path'] != p['path']):
        raise ValueError('Native project/account/path/namespace authorization differs')
    if (not routes or any(r['id'] in initial['route_ids'] or r['path'] != path
        or (r['source_type'], r['source_id']) not in (('Project', p['id']), ('Namespace', n['id'])) for r in routes)
        or sum(r['source_type'] == 'Project' for r in routes) != 1
        or auth != [{'user_id': account, 'project_id': p['id'], 'access_level': 50}]
        or len(members) > 1 or any(r['id'] in initial['member_ids'] or r['user_id'] != account
            or r['source_type'] != 'Project' or r['source_id'] != p['id']
            or r['access_level'] != 50 or r['type'] != 'ProjectMember' for r in members)):
        raise ValueError('Native created project routes/owner-only authorization differs')
    expected = {'projects': [{'id': p['id']}], 'namespaces': [{'id': n['id']}],
        'routes': [{'id': r['id']} for r in routes],
        'project_authorizations': [{'user_id': account, 'project_id': p['id'], 'access_level': 50}],
        'members': [{'id': r['id']} for r in members]}
    if effects['excluded_row_keys'] != expected: raise ValueError('Exact authorized new native keys differ')
    return True

def creation_refs_guard(before, after, effects):
    validate_refs(before); validate_refs(after)
    if effects['created_project'] is None: return before == after
    p = effects['created_project']; target = target_repository({'identity': p['id']})
    a, b = before['repositories'], after['repositories']
    if any(b.get(k) != v for k, v in a.items()): return False
    new = set(b) - set(a)
    if new - {target, target[:-4] + '.wiki.git'}: return False
    # A real saved blank or interrupted import can lack a repository. That is
    # a task failure, not an authorized excuse to mutate unrelated repositories.
    if target not in new and new: return False
    wiki = target[:-4] + '.wiki.git'
    if wiki in new and (b[wiki]['head'] is not None or b[wiki]['refs']): return False
    return True

def _run_ruby(site, script, args, directory, *, seconds=300):
    native_name = 'remaining-private-' + uuid.uuid4().hex
    folder = site.state / native_name; folder.mkdir(mode=0o700)
    atomic_write_json(folder / 'request.json', args)
    (folder / 'reader.rb').write_text(script); (folder / 'reader.rb').chmod(0o600)
    from lab_generate_skill.native_invocation_receipt import invoke_with_receipt
    command = ['bash', '/state/service.sh', 'gitlab-rails', 'env',
        'RAILS_ENV=production', 'LAB_REMAINING_REQUEST=/state/' + native_name + '/request.json',
        '/opt/gitlab/embedded/bin/bundle', 'exec', '/opt/gitlab/embedded/service/gitlab-rails/bin/rails',
        'runner', '-e', 'production', '/state/' + native_name + '/reader.rb']
    result = invoke_with_receipt(
        lambda: native_command(site, command, seconds=seconds),
        directory=directory, script=script, request=args,
        metadata={'native_site_state_path': str(site.state),
                  'native_reference_directory': native_name})
    if result.returncode != 0: raise component.PendingCapability('Bounded private native reference invocation failed')
    reference = json.loads((folder / 'reference.json').read_text())
    directory = Path(directory)
    atomic_write_json(directory / 'native-reference.json', reference)
    return reference

def template_job(before, after, project_id):
    """One genuinely new native local-import job; preserve prior raw queues."""
    old = Counter((r['queue'], r['raw']) for r in before)
    current = Counter((r['queue'], r['raw']) for r in after)
    if old - current: raise ValueError('Existing native jobs disappeared before local template import')
    new = current - old
    found = [r for r in after if new[(r['queue'], r['raw'])] > 0
        and r['job'].get('class') == 'RepositoryImportWorker' and r['job'].get('args') == [project_id]]
    if len(found) != 1 or new[(found[0]['queue'], found[0]['raw'])] != 1:
        raise component.PendingCapability('One actual newly queued local template RepositoryImportWorker required')
    value = found[0]
    if json.loads(value['raw']) != value['job'] or not re.fullmatch('[0-9a-f]{24,32}', value['job'].get('jid', '')):
        raise ValueError('Exact unchanged native local import queue payload required')
    return value

def consume_template_import(site, c, private, queue_before, directory):
    from lab_generate_skill.gitlab_native_csv_probe import queue_snapshot, claim_job, existing_jobs_preserved
    final = __import__('lab_generate_skill.gitlab_project_creation', fromlist=['project_state']).project_state(site, private['baseline']['project_state']['user']['username'])
    effects = authorized_creation(site, c, private['baseline'], final)
    p = effects['created_project']
    if p is None: return None
    current = queue_snapshot(site, Path(directory) / 'template-queue-progress.jsonl')
    record = template_job(queue_before, current, p['id'])
    claim = claim_job(site, record)
    actual = _run_ruby(site, Path(__file__).with_name('native_template_worker.rb').read_text(),
        {'job': record['job'], 'project_id': p['id'], 'account_id': private['baseline']['project_state']['user']['id'],
         'full_path': p['full_path']}, Path(directory) / 'template-native-worker', seconds=300)
    after = queue_snapshot(site, Path(directory) / 'template-queue-progress.jsonl')
    if not existing_jobs_preserved(queue_before, after, [record['job']['jid']]):
        raise ValueError('Original native queues changed during bounded template import')
    result = {'before': queue_before, 'after_request': current, 'after_worker': after,
        'record': record, 'claim': claim, 'native_worker': actual}
    atomic_write_json(Path(directory) / 'template-native-worker-receipt.json', result)
    return result

def native_template(site, directory, *, template_id='plainhtml'):
    script = Path(__file__).with_name('native_template_reference.rb').read_text()
    return _run_ruby(site, script, {'template_id': template_id}, directory)

def capture_csv_chain(site):
    from lab_generate_skill.gitlab_native_csv_admission import CHAIN_FILES
    base = '/opt/gitlab/embedded/service/gitlab-rails/'
    result = site.command(['sha256sum', *[base + p for p in sorted(CHAIN_FILES)]],
        capture_output=True, text=True, timeout=40)
    if result.returncode != 0: raise component.PendingCapability('Actual complete native CSV source chain unavailable')
    chain = {}
    for line in result.stdout.splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch('[0-9a-f]{64}', parts[0]) or not parts[1].startswith(base):
            raise component.PendingCapability('Malformed actual native CSV source fingerprint')
        path = parts[1][len(base):]
        if path in chain: raise ValueError('Duplicate actual native CSV source fingerprint')
        chain[path] = parts[0]
    if set(chain) != CHAIN_FILES: raise component.PendingCapability('Complete native CSV source chain required')
    return chain

def native_csv_reference(site, project_id, account_id, directory):
    from lab_generate_skill import gitlab_native_csv_probe
    asset = Path(gitlab_native_csv_probe.__file__).with_name('gitlab_native_csv_consumer.rb').read_text()
    prefix, separator, _ = asset.partition('jobs=JSON.parse')
    if not separator: raise ValueError('Exact installed independent raw CSV reference module unavailable')
    script = prefix + r'''
args=JSON.parse(File.read(ENV.fetch('LAB_REMAINING_REQUEST')))
value=LabIndependentCsvReference.raw_reference('merge_request',args.fetch('account_id'),args.fetch('project_id'),{'state'=>'all'},args.fetch('origin'))
File.open(File.join(File.dirname(ENV.fetch('LAB_REMAINING_REQUEST')),'reference.json'),File::WRONLY|File::CREAT|File::EXCL,0600){|f|f.write(JSON.generate(value))}
puts 'LAB_REMAINING_NATIVE_REFERENCE_COMPLETE'
'''
    reference = _run_ruby(site, script, {'project_id': project_id, 'account_id': account_id, 'origin': site.url}, directory)
    return normalize_reference(reference, site.url)
