"""Terminal account state, distinct from registration progress and reset checks.

Only public account identity and native confirmation/session facts are scored.
Credentials and confirmation tokens never enter evaluator feedback. A successful
account task need not end on the settings page; its session is read separately.
"""
from urllib.parse import urlsplit

VERSION = 'native-map-account-terminal-v1'
FAMILIES = {'account_signup', 'account_login'}


def public_goal(candidate):
    """Make the contract's supplied training credentials visible to the actor."""
    spec = candidate['candidate_completion']
    if spec.get('family') not in FAMILIES:
        raise ValueError('Native account task required')
    account = spec['public_account']
    if set(account) != {'email', 'display_name', 'password'} or not all(
            isinstance(v, str) and v and '\n' not in v and '\r' not in v for v in account.values()):
        raise ValueError('Complete one-line public training account required')
    if not account['email'].endswith('@example.test'):
        raise ValueError('Local training account required')
    return (candidate['goal'] + '\n\nSupplied local account details:\n'
            + '\n'.join(f'{label}: {account[key]}' for key, label in
                        [('email', 'Email'), ('display_name', 'Display name'), ('password', 'Password')]))


def _record(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get('captured') is not True or 'target' not in snapshot:
        raise ValueError('Explicit native account readout required')
    row = snapshot['target']
    if row is not None and (not isinstance(row, dict) or type(row.get('id')) is not int
            or row['id'] <= 0 or type(row.get('email_valid')) is not bool
            or any(not isinstance(row.get(k), str) or not row[k] for k in ('email', 'display_name', 'status'))):
        raise ValueError('Native account fields unavailable')
    return row


def evaluate_account(spec, *, initial, final, session, origin,
                     runtime_error=None, capture_error=None, integrity=True):
    if spec.get('family') not in FAMILIES:
        raise ValueError('Explicit signup or login goal required')
    target = spec['public_account']
    checks = {}
    def result(status, reason):
        return dict(version=VERSION, status=status,
                    reward={'success': 1., 'failure': 0., 'unknown': None}[status],
                    checks=checks, reason=reason)
    if runtime_error or capture_error or integrity is not True:
        return result('unknown', 'Runtime, account capture or instance integrity unavailable.')
    try:
        before, after = _record(initial), _record(final)
    except ValueError:
        return result('unknown', 'Initial or final database readout is incomplete.')
    identity = lambda row: row is not None and all(row[k] == target[k] for k in ('email', 'display_name'))
    confirmed = lambda row: row is not None and row['email_valid'] is True and row['status'] in ('active', 'confirmed')
    if spec['family'] == 'account_signup':
        if before is not None:
            return result('unknown', 'Signup target was already present before execution.')
    elif not identity(before) or not confirmed(before):
        return result('unknown', 'Declared existing account was not available initially.')
    # Probe transport/capture failures are not an anonymous session or actor failure.
    if not isinstance(session, dict) or type(session.get('http_status')) is not int:
        return result('unknown', 'Authenticated-session observation unavailable.')
    status = session['http_status']
    if not 200 <= status < 400 or type(session.get('native_settings_form')) is not bool:
        return result('unknown', 'Native account-session probe failed.')
    actual, expected = urlsplit(session.get('url', '')), urlsplit(origin)
    if (actual.scheme, actual.netloc) != (expected.scheme, expected.netloc):
        return result('unknown', 'Native session probe left its isolated website.')
    authenticated = session['native_settings_form']
    if authenticated:
        if (status != 200 or actual.path != '/account/edit'
                or any(not isinstance(session.get(k), str) or not session[k] for k in ('email', 'display_name'))):
            return result('unknown', 'Incomplete native authenticated account form.')
    elif status != 200 or actual.path != '/login':
        return result('unknown', 'Unrecognized native anonymous-session response.')
    checks['target_account_exists'] = after is not None
    checks['target_account_identity_matches'] = identity(after)
    checks['native_confirmation_complete'] = confirmed(after)
    checks['signed_in_to_requested_account'] = authenticated and all(
        session[k] == target[k] for k in ('email', 'display_name'))
    return result('success' if all(checks.values()) else 'failure',
                  'Native saved account, confirmation and terminal session checked.')


def feedback(judgment):
    if judgment.get('version') != VERSION:
        raise ValueError('Native account terminal judgment required')
    return dict(status=judgment['status'], reward=judgment['reward'],
                checks=[dict(condition=k, passed=v) for k, v in judgment['checks'].items() if type(v) is bool],
                private_reference_values_provided=False, action_sequence_provided=False)
