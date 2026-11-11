"""Private native persistence checks for generic/named forum creation only."""
from .reddit_submission import submission_state
from .site_database import select_rows
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint

VERSION = 'reddit-forum-creation-v1'
ADMISSION_VERSION = 'reddit-forum-creation-admission-v1'


def validate_contract(c):
    spec = c['forum_creation']
    if c.get('domain') != 'reddit' or set(spec) != {'name'}:
        raise ValueError('Unsupported forum creation requirement')
    if spec['name'] is not None and (not isinstance(spec['name'], str) or not spec['name'].strip()):
        raise ValueError('Invalid requested forum name')


def forum_state(site, username, baseline=None):
    return {'forums': select_rows(site, 'SELECT id,name,title,description,sidebar FROM forums ORDER BY id'),
            'submissions': submission_state(site, username, baseline['submissions'] if baseline else None)}


def validate_initial(c, state):
    validate_contract(c)
    if not isinstance(state, dict) or not state.get('forums') or state['submissions']['added']:
        raise ValueError('Missing or dirty forum baseline')
    name = c['forum_creation']['name']
    if name and any(r['name'].casefold() == name.casefold() for r in state['forums']):
        raise ValueError('Requested new forum already exists')


def fingerprint(c):
    return reference_fingerprint({k: c.get(k) for k in ('task_id', 'source_task_id', 'domain', 'goal',
        'start_path', 'forum_creation', 'heldout_quarantine', 'start_revision', 'goal_revision', 'initial_page_policy')})


def evaluate_forum(c, page, initial, final, *, site_origin, runtime_error=None):
    validate_contract(c)
    def unknown(reason):
        return {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': {}, 'reason': reason}
    if runtime_error:
        return unknown('Environment or inference error')
    if not isinstance(page, dict) or type(page.get('http_status')) is not int or not 200 <= page['http_status'] < 500:
        return unknown('Missing terminal page or transport/server error')
    if not initial or not final:
        return unknown('Missing forum state')
    before, after = initial['submissions'], final['submissions']
    if before['user_id'] != after['user_id'] or before['known_id_ranges'] != after['known_id_ranges']:
        return unknown('Mismatched account or submission baseline')
    original = {r['id']: r for r in initial['forums']}
    current = {r['id']: r for r in final['forums']}
    added = [r for r in final['forums'] if r['id'] not in original]
    checks = {'page_valid': valid_initial_page(page, site_origin=site_origin),
              'existing_forums_unchanged': all(current.get(k) == v for k, v in original.items()),
              'submissions_unchanged': before['protected_content'] == after['protected_content'] and after['added'] == [],
              'one_forum_saved': len(added) == 1}
    if len(added) == 1:
        row = added[0]
        checks['requested_name'] = c['forum_creation']['name'] is None or row['name'] == c['forum_creation']['name']
        checks['required_fields_saved'] = all(isinstance(row[k], str) and bool(row[k].strip())
                                              for k in ('name', 'title', 'description', 'sidebar'))
    passed = all(checks.values())
    return {'version': VERSION, 'status': 'success' if passed else 'failure', 'reward': float(passed),
            'checks': checks, 'reason': None}


def expected_controls(c):
    checks = dict.fromkeys(('no_op', 'filled_unsaved', 'invalid_form', '404', 'login'), 'failure')
    if c['forum_creation']['name'] is not None:
        checks['wrong_name'] = 'failure'
    return checks | {'positive': 'success', 'saved_then_home': 'success'}


def forum_feedback(j):
    labels = {'page_valid': 'The final page is a valid page on the task website.',
              'existing_forums_unchanged': 'Previously existing forums remain unchanged.',
              'submissions_unchanged': 'Previously existing posts remain unchanged and no unrelated post was added.',
              'one_forum_saved': 'One new forum has actually been saved.',
              'requested_name': 'The saved name satisfies the task requirement.',
              'required_fields_saved': 'The native required forum fields were saved.'}
    return {'status': j['status'], 'reward': j['reward'], 'reason': j.get('reason'),
            'checks': [{'name': k, 'passed': v, 'condition': labels[k]} for k, v in j['checks'].items()],
            'action_sequence_provided': False, 'reference_values_provided': False}


def require_forum_admission(c, proof):
    validate_contract(c)
    if c.get('heldout_quarantine') or proof.get('admission_version') != ADMISSION_VERSION or proof.get('contract_fingerprint') != fingerprint(c):
        raise ValueError('Stale or quarantined forum admission')
    rows = proof.get('cycles', [])
    if not proof.get('passed') or len(rows) != 2 or proof.get('reset_mode') != 'fresh_site_per_task_cycle':
        raise ValueError('Two independent full site deployments required')
    for row in rows:
        validate_initial(c, row.get('initial_state'))
        if not row.get('passed') or not row.get('initial_valid') or row.get('checks') != expected_controls(c):
            raise ValueError('Incomplete native forum controls')
        if not row.get('initial_fingerprint') or row['initial_fingerprint'] != row.get('final_fingerprint'):
            raise ValueError('Protected account state changed')
        if c['forum_creation']['name'] is not None:
            wrong = row.get('wrong_name_control', {})
            if wrong.get('initial_state') != row['initial_state'] or not wrong.get('one_wrong_forum_saved') or not wrong.get('accounts_unchanged'):
                raise ValueError('Wrong-name control did not independently create one wrong forum')
    if rows[0]['initial_state'] != rows[1]['initial_state'] or rows[0]['initial_fingerprint'] != rows[1]['initial_fingerprint']:
        raise ValueError('Fresh forum reset baselines differ')
