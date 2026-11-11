"""Private persisted issue-creation evaluation, independent of actor actions.

Generic creation goals permit any nonempty native title. This evaluator does
not assess writing quality or silently replace semantic requirements with
keyword checks. Explicit project/title/body requirements remain exact.
"""
from .site_database import select_rows
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint

VERSION = 'gitlab-issue-creation-v1'
ADMISSION_VERSION = 'gitlab-issue-creation-admission-v1'


def validate_contract(c):
    s = c.get('issue_creation')
    if c.get('domain') != 'gitlab' or not isinstance(s, dict) or set(s) != {'project_path', 'title', 'description'}:
        raise ValueError('Unsupported issue creation contract')
    for k, v in s.items():
        if v is not None and (not isinstance(v, str) or not v.strip()):
            raise ValueError('Invalid issue condition: ' + k)


def issue_state(site, username, *, baseline=None, compact=False):
    if compact or (baseline and baseline.get('encoding')):
        from .gitlab_issue_compact import read
        return read(site, username, baseline=baseline, select=select_rows)
    name = "'" + username.replace("'", "''") + "'"
    users = select_rows(site, 'SELECT id,username FROM users WHERE username=' + name)
    if len(users) != 1:
        raise ValueError('Missing or ambiguous issue author')
    return {'user': users[0],
            'projects': select_rows(site, "SELECT p.id,p.name,r.path FROM projects p JOIN routes r ON r.source_id=p.id AND r.source_type='Project' ORDER BY p.id"),
            'issues': select_rows(site, 'SELECT id,iid,project_id,author_id,title,description,state_id,confidential FROM issues ORDER BY id')}


def validate_initial(c, state):
    validate_contract(c)
    if not isinstance(state, dict) or not isinstance(state.get('user'), dict) or not isinstance(state.get('projects'), list):
        raise ValueError('Missing native issue baseline')
    if state.get('encoding'):
        from .gitlab_issue_compact import validate
        validate(state, initial=True)
    elif not isinstance(state.get('issues'), list):
        raise ValueError('Missing original issue records')
    path = c['issue_creation']['project_path']
    if path is not None and len([r for r in state['projects'] if r['path'] == path]) != 1:
        raise ValueError('Requested project absent or ambiguous')


def evaluate_issue(c, page, initial, final, *, site_origin, runtime_error=None):
    def unknown(reason):
        return {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': {}, 'reason': reason}
    if runtime_error:
        return unknown('Environment or inference error')
    try:
        validate_initial(c, initial)
    except (ValueError, KeyError, TypeError) as exc:
        return unknown(str(exc))
    if not isinstance(page, dict) or type(page.get('http_status')) is not int or not 200 <= page['http_status'] < 500:
        return unknown('Missing terminal page or transport/server error')
    if not isinstance(final, dict) or final.get('user') != initial['user'] or not isinstance(final.get('projects'), list):
        return unknown('Missing final issue state or changed author binding')
    if initial.get('encoding'):
        from .gitlab_issue_compact import validate
        try: validate(final)
        except ValueError as exc: return unknown(str(exc))
        if initial['known_id_ranges'] != final['known_id_ranges']:
            return unknown('Protected issue ID baseline changed')
        unchanged = initial['protected_issues'] == final['protected_issues']
        added = final['added_issues']
    else:
        if not isinstance(final.get('issues'), list): return unknown('Missing original issue records')
        old = {r['id']: r for r in initial['issues']}
        now = {r['id']: r for r in final['issues']}
        added = [r for r in final['issues'] if r['id'] not in old]
        unchanged = all(now.get(k) == v for k, v in old.items())
    projects = {r['id']: r['path'] for r in initial['projects']}
    checks = {'page_valid': valid_initial_page(page, site_origin=site_origin),
              'projects_unchanged': initial['projects'] == final['projects'],
              'existing_issues_unchanged': unchanged,
              'one_issue_saved': len(added) == 1}
    if len(added) == 1:
        r, s = added[0], c['issue_creation']
        checks.update(correct_author=r['author_id'] == initial['user']['id'],
                      requested_project=r['project_id'] in projects and (s['project_path'] is None or projects[r['project_id']] == s['project_path']),
                      title_saved=isinstance(r['title'], str) and bool(r['title'].strip()))
        for field in ('title', 'description'):
            if s[field] is not None:
                checks['requested_' + field] = r[field] == s[field]
    passed = all(checks.values())
    return {'version': VERSION, 'status': 'success' if passed else 'failure', 'reward': float(passed), 'checks': checks, 'reason': None}


def fingerprint(c):
    keys = ('task_id', 'source_task_id', 'domain', 'goal', 'start_path', 'issue_creation', 'heldout_quarantine', 'start_revision', 'goal_revision')
    if 'issue_state_encoding' in c: keys += ('issue_state_encoding',)
    return reference_fingerprint({k: c.get(k) for k in keys})


def expected_controls(c):
    checks = dict.fromkeys(('no_op', 'filled_unsaved', 'invalid_form', '404', 'login'), 'failure')
    checks.update(positive='success', saved_then_home='success')
    for field in ('project_path', 'title', 'description'):
        if c['issue_creation'][field] is not None:
            checks['wrong_' + ('project' if field == 'project_path' else field)] = 'failure'
    return checks


def feedback(j):
    labels = {'page_valid': 'The final page is valid on the task website.',
              'projects_unchanged': 'Existing projects remain unchanged.',
              'existing_issues_unchanged': 'Previously existing issues remain unchanged.',
              'one_issue_saved': 'One new issue has actually been saved.',
              'correct_author': 'The new issue belongs to the task account.',
              'requested_project': 'The issue is saved in a project allowed by the task.',
              'title_saved': 'The native required title is nonempty and saved.',
              'requested_title': 'The saved title matches the task requirement.',
              'requested_description': 'The saved description matches the task requirement.'}
    return {'status': j['status'], 'reward': j['reward'], 'reason': j.get('reason'),
            'checks': [{'name': k, 'passed': v, 'condition': labels[k]} for k, v in j['checks'].items()],
            'action_sequence_provided': False, 'reference_values_provided': False}


def require_admission(c, proof):
    validate_contract(c)
    if c.get('heldout_quarantine') or proof.get('admission_version') != ADMISSION_VERSION or proof.get('contract_fingerprint') != fingerprint(c):
        raise ValueError('Stale or quarantined issue admission')
    rows = proof.get('cycles', [])
    if proof.get('passed') is not True or len(rows) != 2 or proof.get('reset_mode') != 'fresh_site_per_task_cycle':
        raise ValueError('Two independent native issue cycles required')
    for r in rows:
        validate_cycle(c, r)
    if rows[0]['initial_state'] != rows[1]['initial_state'] or rows[0]['initial_fingerprint'] != rows[1]['initial_fingerprint']:
        raise ValueError('Independent issue reset baselines differ')


def validate_cycle(c, r):
    """Validate one existing native cycle without pretending it is two resets."""
    validate_contract(c)
    validate_initial(c, r.get('initial_state'))
    if c.get('issue_state_encoding') != r['initial_state'].get('encoding'):
        raise ValueError('Issue contract and proof use different state encodings')
    if r.get('passed') is not True or r.get('initial_valid') is not True or r.get('checks') != expected_controls(c):
        raise ValueError('Incomplete issue controls')
    if not r.get('initial_fingerprint') or r['initial_fingerprint'] != r.get('final_fingerprint'):
        raise ValueError('Protected project records changed')
    for name in expected_controls(c):
        if not name.startswith('wrong_'):
            continue
        neg = r.get('independent_negatives', {}).get(name, {})
        if neg.get('initial_state') != r['initial_state'] or neg.get('isolated_wrong_condition') is not True or neg.get('protected_projects_unchanged') is not True:
            raise ValueError('Negative issue condition not independently isolated')
