"""Saved Reddit hidden-forum membership; private references never guide actions."""
from urllib.parse import urlsplit
from .site_database import select_rows
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint

VERSION = 'reddit-hidden-membership-v1'
ADMISSION_VERSION = 'reddit-hidden-membership-admission-v1'
EXPECTED_CONTROLS = {'no_op': 'failure', 'wrong_forum': 'failure', 'positive': 'success',
                     '404': 'failure', 'anonymous_login': 'failure'}
REFERENCE_CONTROLS = {'wrong_user_reference': 'failure'}


def _positive(value):
    if type(value) is not int or value <= 0: raise ValueError('Positive integer identity required')
    return value


def validate(contract):
    spec = contract['membership']
    if contract.get('domain') != 'reddit' or spec.get('collection') != 'hidden_forums':
        raise ValueError('Explicit Reddit hidden-forum collection required')
    _positive(spec['object_id'])
    if type(spec.get('desired_present')) is not bool: raise ValueError('Boolean target state required')
    account = spec['account']; _positive(account['id'])
    if not isinstance(account.get('username'), str) or not account['username']: raise ValueError('Bound account required')
    u = urlsplit(spec['object_path'])
    if u.scheme or u.netloc or not u.path.startswith('/f/') or u.query or u.fragment:
        raise ValueError('Exact native forum path required')
    return spec


def _pairs(rows):
    if not isinstance(rows, list): raise ValueError('Saved memberships must be a list')
    pairs = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'user_id', 'forum_id'}: raise ValueError('Invalid membership row')
        pairs.append((_positive(row['user_id']), _positive(row['forum_id'])))
    if len(set(pairs)) != len(pairs) or pairs != sorted(pairs): raise ValueError('Memberships must be unique and ordered')
    return set(pairs)


def validate_state(state):
    if not isinstance(state, dict): raise ValueError('Missing saved state')
    account = state['account']; _positive(account['id'])
    if not isinstance(account.get('username'), str) or not account['username']: raise ValueError('Invalid saved account')
    _pairs(state['hidden_forums']); _pairs(state['forum_subscriptions'])
    return state


def hidden_membership_state(site, username):
    if site.domain != 'reddit' or not isinstance(username, str) or not username: raise ValueError('Reddit account required')
    user = select_rows(site, "SELECT id,username FROM users WHERE username='" + username.replace("'", "''") + "'")
    if len(user) != 1: raise ValueError('Account missing or ambiguous')
    state = {'account': user[0],
             'hidden_forums': select_rows(site, 'SELECT user_id,forum_id FROM hidden_forums ORDER BY user_id,forum_id'),
             'forum_subscriptions': select_rows(site, 'SELECT user_id,forum_id FROM forum_subscriptions ORDER BY user_id,forum_id')}
    return validate_state(state)


def verify_reference(site, contract):
    spec = validate(contract)
    user = select_rows(site, 'SELECT id,username FROM users WHERE id=' + str(spec['account']['id']))
    forum = select_rows(site, 'SELECT id,name FROM forums WHERE id=' + str(spec['object_id']))
    if user != [spec['account']] or len(forum) != 1 or '/f/' + forum[0]['name'] != spec['object_path']:
        raise ValueError('Native account or forum identity changed')
    return {'account': user[0], 'forum': forum[0]}


def evaluate_hidden_membership(contract, page, initial, final, *, site_origin, runtime_error=None):
    spec = validate(contract)
    def unknown(reason): return {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': {}, 'reason': reason}
    if runtime_error: return unknown('Runtime failure')
    try: validate_state(initial); validate_state(final)
    except (ValueError, KeyError, TypeError): return unknown('Missing or malformed saved account/membership state')
    if initial['account'] != spec['account']: return unknown('Initial account reference differs from binding')
    if (not isinstance(page, dict) or type(page.get('http_status')) is not int
            or page['http_status'] < 200 or page['http_status'] >= 500):
        return unknown('Missing terminal capture or server failure')
    target = (spec['account']['id'], spec['object_id'])
    before = _pairs(initial['hidden_forums']); after = _pairs(final['hidden_forums'])
    checks = {'page_valid': valid_initial_page(page, site_origin=site_origin),
              'account_reference': final['account'] == spec['account'],
              'target_hidden_membership': (target in after) == spec['desired_present'],
              'other_hidden_memberships_unchanged': before - {target} == after - {target},
              'forum_subscriptions_unchanged': initial['forum_subscriptions'] == final['forum_subscriptions']}
    passed = all(checks.values())
    return {'version': VERSION, 'status': 'success' if passed else 'failure', 'reward': float(passed), 'checks': checks, 'reason': None}


def feedback(judgment):
    descriptions = {'page_valid': 'The final page is a valid local website page.',
                    'account_reference': 'The saved state belongs to the bound task account.',
                    'target_hidden_membership': 'The requested forum has the requested saved hidden state.',
                    'other_hidden_memberships_unchanged': 'Other accounts and forums have unchanged hidden states.',
                    'forum_subscriptions_unchanged': 'Forum subscriptions remain unchanged.'}
    return {'status': judgment['status'], 'reward': judgment['reward'], 'reason': judgment.get('reason'),
            'checks': [{'name': k, 'passed': v, 'condition': descriptions[k]} for k, v in judgment['checks'].items()],
            'action_sequence_provided': False}


def contract_fingerprint(contract):
    return reference_fingerprint({k: contract.get(k) for k in ('task_id', 'source_task_id', 'domain', 'goal', 'start_path',
                                                            'membership', 'heldout_quarantine', 'task_version')})


def control_admission(contract, cases, *, site_origin):
    required = set(EXPECTED_CONTROLS) | set(REFERENCE_CONTROLS)
    if set(cases) != required: raise ValueError('All actual controls and separately labeled account reference control required')
    checks = {name: evaluate_hidden_membership(contract, row['page'], row['initial_state'], row['final_state'],
                                              site_origin=site_origin)['status'] for name, row in cases.items()}
    return {'passed': checks == EXPECTED_CONTROLS | REFERENCE_CONTROLS,
            'checks': {k: checks[k] for k in EXPECTED_CONTROLS},
            'reference_checks': {k: checks[k] for k in REFERENCE_CONTROLS},
            'wrong_user_reference_scope': 'Independent alternate DB account reference; not another authenticated UI session.'}


def require_admission(contract, proof):
    validate(contract)
    if contract.get('heldout_quarantine') is not False: raise ValueError('Heldout or unknown split cannot be admitted')
    if proof.get('admission_version') != ADMISSION_VERSION or proof.get('contract_fingerprint') != contract_fingerprint(contract):
        raise ValueError('Stale hidden-membership admission proof')
    cycles = proof.get('cycles', [])
    if proof.get('passed') is not True or len(cycles) != 2: raise ValueError('Two actual fresh cycles required')
    for cycle in cycles:
        if (cycle.get('passed') is not True or cycle.get('checks') != EXPECTED_CONTROLS
                or cycle.get('reference_checks') != REFERENCE_CONTROLS or cycle.get('restored') is not True
                or cycle.get('private_reference_equal') is not True or cycle.get('protected_records_unchanged') is not True
                or cycle.get('initial_state') != cycle.get('final_state') or cycle.get('initial_fingerprint') != cycle.get('final_fingerprint')):
            raise ValueError('Actual negative controls and complete restoration required')
        validate_state(cycle['initial_state'])
        if cycle['initial_state']['account'] != contract['membership']['account']: raise ValueError('Wrong reset account')
        if cycle.get('native_controls_verified') is not True: raise ValueError('Native UI positive and wrong-forum evidence required')
        if cycle.get('reference_verified_before_after') is not True: raise ValueError('Native reference changed during controls')
    if cycles[0]['initial_state'] != cycles[1]['initial_state'] or cycles[0]['initial_fingerprint'] != cycles[1]['initial_fingerprint']:
        raise ValueError('Reset baselines differ')
