"""Native callback port; source controls and scoring preserved."""
from copy import deepcopy

import re

from lab_generate_skill.source_revision_binding import binding, require_source_binding

from lab_generate_skill.gitlab_native_read_runtime import full_snapshot

from lab_generate_skill.gitlab_persisted_goal_runtime import validate_refs

from lab_generate_skill.site_navigation_rules import valid_initial_page

from lab_generate_skill import gitlab_grouped_goal_runtime as grouped

from lab_generate_skill import gitlab_native_csv_runtime as csv_runtime

from lab_generate_skill import gitlab_native_csv_admission as csv_admission

from lab_generate_skill.gitlab_project_creation import validate_state, existing_unchanged

from . import gitlab_remaining_public as public

VERSION = 'gitlab-remaining-native-components-v1'

KINDS = {'native_group_hierarchy', 'native_monitoring_section',
         'native_all_merge_request_csv', 'native_repository_template'}

SHA = re.compile('[0-9a-f]{64}')

OID = re.compile('[0-9a-f]{40}(?:[0-9a-f]{24})?')

class PendingCapability(ValueError):
    """Missing environment/factory qualification is unknown, not actor failure."""

def enabled(c):
    if c.get('family') not in KINDS:
        raise ValueError('Unsupported remaining native family')
    if c.get('domain') != 'gitlab' or c.get('eligible_for_training') is not False:
        raise ValueError('Unadmitted GitLab candidate required')
    binding(c)
    p = c.get('public_parameters')
    if not isinstance(p, dict): raise ValueError('Explicit public parameters required')
    if c.get('public_task_input', {}).get('goal') != c['goal'] or c['public_task_input'].get('public_parameters') != p:
        raise ValueError('Generator and actor must receive identical explicit task parameters')
    return True

def public_goal(c):
    enabled(c)
    return public.render(c)

def metrics_reference(site, c):
    from lab_generate_skill.gitlab_metrics_fixture import feature_state
    value = grouped.reference(site, c)
    value['metrics_feature_state'] = feature_state(site)
    return value

def metrics_checks(c, page, private_reference, *, site_origin, runtime_error=None):
    """Installed page/section checks; genuine page access is not metric retrieval."""
    enabled(c); grouped.enabled(c)
    return grouped.evaluate(c, page, private_reference, site_origin=site_origin, runtime_error=runtime_error)

from lab_generate_skill import gitlab_group_tree

HIERARCHY_READ = gitlab_group_tree.READ

def capture_hierarchy(page):
    return page.evaluate(HIERARCHY_READ)

def hierarchy_reference(site, username):
    """Full independent native group tree, not the actor's chosen target."""
    from lab_generate_skill.site_database import select_rows
    from lab_generate_skill.gitlab_directory import directory_access_reference
    access = directory_access_reference(site, username)
    rows = select_rows(site, "SELECT n.id,n.parent_id,r.path FROM namespaces n JOIN routes r "
        "ON r.source_type='Namespace' AND r.source_id=n.id WHERE n.type='Group' ORDER BY n.id")
    ref = {'account_id': access['user']['id'], 'groups': rows}
    validate_hierarchy_reference(ref)
    return ref

def validate_hierarchy_reference(ref):
    if not isinstance(ref, dict) or type(ref.get('account_id')) is not int or ref['account_id'] <= 0:
        raise ValueError('Independent actual native account reference required')
    rows = ref.get('groups')
    if not isinstance(rows, list) or not rows:
        raise PendingCapability('Native group hierarchy is absent')
    if any(not isinstance(r, dict) or set(r) != {'id', 'parent_id', 'path'}
           or type(r['id']) is not int or r['id'] <= 0
           or r['parent_id'] is not None and (type(r['parent_id']) is not int or r['parent_id'] <= 0)
           or not isinstance(r['path'], str) or not re.fullmatch(r'[\w.-]+(?:/[\w.-]+)*', r['path']) for r in rows):
        raise ValueError('Full native group hierarchy schema required')
    by = {r['id']: r for r in rows}
    if len(by) != len(rows) or len({r['path'] for r in rows}) != len(rows): raise ValueError('Duplicate native group identity')
    for r in rows:
        parent = r['parent_id']; seen = {r['id']}
        if parent is not None and parent in by and not r['path'].startswith(by[parent]['path'] + '/'):
            raise ValueError('Native group route and recorded parent ancestry differ')
        while parent is not None:
            if parent not in by or parent in seen: raise ValueError('Incomplete or cyclic native group ancestry')
            seen.add(parent); parent = by[parent]['parent_id']
    eligible = [r for r in rows if r['parent_id'] is not None and any(x['parent_id'] == r['id'] for x in rows)]
    if not eligible: raise PendingCapability('No real subgroup with nested subgroups exists in the native seed')
    return eligible

def hierarchy_checks(c, capture, reference):
    enabled(c)
    if c['family'] != 'native_group_hierarchy': raise ValueError('Group hierarchy candidate required')
    eligible = validate_hierarchy_reference(reference)
    if (not isinstance(capture, dict) or capture.get('capture_truncated') is not False
        or not isinstance(capture.get('rows'), list) or not isinstance(capture.get('body_page'), str)):
        raise PendingCapability('Actual complete native group DOM schema unavailable')
    # The initial native capability gate must establish that these stable data
    # attributes and explicit expanded controls are present. Missing attributes
    # are a capability gap, never guessed from an anchor or a private SQL row.
    rows = capture['rows']
    if any(not isinstance(r, dict) or set(r) != {'id', 'links', 'expanded_controls', 'own_expanded'}
           or not isinstance(r['id'], str) or not r['id'].isdigit()
           or not isinstance(r['links'], list) or not isinstance(r['expanded_controls'], list)
           or any(not isinstance(a, dict) or set(a) != {'path', 'text'}
                  or not isinstance(a['path'], str) or not isinstance(a['text'], str) for a in r['links'])
           or any(not isinstance(e, dict) or set(e) != {'role', 'expanded'}
                  or e['expanded'] not in ('true', 'false') for e in r['expanded_controls'])
           or r['own_expanded'] not in (None, 'true', 'false') for r in rows):
        raise PendingCapability('Actual native group row/control schema unavailable')
    if len({r['id'] for r in rows}) != len(rows): raise PendingCapability('Ambiguous repeated native group container')
    by = {int(r['id']): r for r in rows}
    visible_paths = {a['path'].rstrip('/') for r in rows for a in r['links']}
    matched = []
    for parent in eligible:
        row = by.get(parent['id'])
        if row is None: continue
        expanded = row['own_expanded'] == 'true' or any(e['expanded'] == 'true' for e in row['expanded_controls'])
        own_identity = '/' + parent['path'] in {a['path'].rstrip('/') for a in row['links']}
        children = [x for x in reference['groups'] if x['parent_id'] == parent['id']]
        visible_child = any(x['id'] in by and '/' + x['path'] in {a['path'].rstrip('/') for a in by[x['id']]['links']} for x in children)
        matched.append(expanded and own_identity and visible_child)
    return {'bound_native_account': capture.get('account_id') == reference['account_id'],
        'native_group_hierarchy_page': bool(re.match(r'^(?:groups|dashboard:groups):', capture['body_page'])),
        'expanded_native_subgroup_with_actual_visible_child': any(matched)}

def hierarchy_terminal(c, page, reference, *, site_origin, full_before, full_after,
                       refs_before, refs_after, reference_after, runtime_error=None):
    """No intermediate reward; a task attempt is scored only after it terminates."""
    try:
        enabled(c); full_snapshot(full_before); full_snapshot(full_after)
        validate_refs(refs_before); validate_refs(refs_after)
        if runtime_error or full_before != full_after or refs_before != refs_after or reference != reference_after:
            raise PendingCapability('Environment, full native state or repository integrity changed')
        if (not isinstance(page, dict) or type(page.get('http_status')) is not int
            or not 200 <= page['http_status'] < 500 or not isinstance(page.get('url'), str)
            or type(page.get('login_page')) is not bool or type(page.get('error_page')) is not bool):
            raise PendingCapability('Terminal native transport capture is missing')
        valid = valid_initial_page(page, site_origin=site_origin)
        if not valid: checks = {'valid_native_page': False}
        else:
            checks = {'valid_native_page': True, **hierarchy_checks(c, page.get('native_hierarchy'), reference)}
        passed = all(checks.values())
        return {'version': VERSION, 'status': 'success' if passed else 'failure', 'reward': float(passed), 'checks': checks, 'reason': None}
    except (PendingCapability, ValueError, KeyError, TypeError) as e:
        return {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': {}, 'reason': str(e)}

def qualify_local_template(catalogue, template_repository, *, template_name):
    """Compare actual independent native template bytes, not a created project.

    The catalogue collector must independently establish source_kind and bundle
    digest from the installed native local template. An arbitrary supplied JSON
    is component input only and cannot constitute a normal admission proof.
    """
    if not isinstance(catalogue, list) or not isinstance(template_name, str): raise ValueError('Actual native local template catalogue required')
    entries = [r for r in catalogue if isinstance(r, dict) and r.get('name') == template_name]
    if len(entries) != 1: raise PendingCapability('Unique named native template unavailable')
    entry = entries[0]
    if (set(entry) != {'name', 'id', 'source_kind', 'native_bundle_sha256', 'repository_files'}
        or not isinstance(entry['id'], str) or not entry['id']
        or entry['source_kind'] != 'native_local_bundle' or not SHA.fullmatch(entry['native_bundle_sha256'])
        or not isinstance(entry['repository_files'], dict) or not entry['repository_files']):
        raise PendingCapability('Qualified actual local native template bundle required; remote or blank fallback is unsupported')
    files = template_repository.get('files') if isinstance(template_repository, dict) else None
    _validate_tree(files)
    if files != entry['repository_files']:
        raise ValueError('Actual complete native template tree differs from independent bundle')
    return deepcopy(entry)

def _validate_tree(files):
    if not isinstance(files, dict) or not files: raise ValueError('Complete populated native repository tree required')
    for path, row in files.items():
        if (not isinstance(path, str) or not path or path.startswith('/') or '\\' in path
            or any(x in ('', '.', '..') for x in path.split('/'))
            or not isinstance(row, dict) or set(row) != {'mode', 'oid'}
            or row['mode'] not in ('100644', '100755', '120000', '160000') or not OID.fullmatch(row['oid'])):
            raise ValueError('Exact complete native repository path/mode/object tree required')
    return files

def template_content_checks(c, initial, final, qualified_template, final_repository):
    """Executable component checks; full authorized native creation is pending.

    A component pass alone never permits inference/training: normal runtime must
    also prove narrowly qualified full16 creation effects and all old repo refs.
    """
    enabled(c)
    if c['family'] != 'native_repository_template': raise ValueError('Template family required')
    public.public_input(c); validate_state(initial); validate_state(final)
    _validate_tree(qualified_template.get('repository_files'))
    if (qualified_template.get('source_kind') != 'native_local_bundle'
        or not SHA.fullmatch(qualified_template.get('native_bundle_sha256', ''))
        or qualified_template.get('name') != c['public_parameters']['template_name']):
        raise PendingCapability('Independent actual public template reference unavailable')
    old = {r['id'] for r in initial['projects']}; created = [r for r in final['projects'] if r['id'] not in old]
    p = c['public_parameters']; checks = {'existing_projects_unchanged': existing_unchanged(initial, final),
        'one_project_saved': len(created) == 1, 'current_account_unchanged': initial['user'] == final['user']}
    if len(created) != 1: return checks
    row = created[0]
    checks.update(created_by_current_account=row['creator_id'] == initial['user']['id'],
        requested_project_name_saved=row['name'] == p['project_name'],
        requested_project_path_saved=row['path'] == p['project_path'],
        actual_saved_repository_identity=final_repository.get('identity') == row['id'])
    head = final_repository.get('head'); branch = final_repository.get('branch'); refs = final_repository.get('refs')
    checks['native_populated_initial_commit'] = (isinstance(head, str) and OID.fullmatch(head) is not None
        and isinstance(branch, str) and branch and isinstance(refs, dict) and refs.get('refs/heads/' + branch) == head)
    try:
        files = _validate_tree(final_repository.get('files'))
        checks['complete_actual_template_repository_tree'] = files == qualified_template['repository_files']
    except ValueError: checks['complete_actual_template_repository_tree'] = False
    return checks

def posterior_feedback(j):
    """Check outcomes only; private records, target values and action paths stay private."""
    return {'status': j['status'], 'reward': j['reward'], 'reason': j.get('reason'),
        'checks': [{'name': k, 'passed': v} for k, v in j.get('checks', {}).items()],
        'reference_values_provided': False, 'action_sequence_provided': False}
