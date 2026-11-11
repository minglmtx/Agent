"""Terminal native page identity with complete sixteen-table reset protection.

No model strategy, redirect, reference injection or mid-rollout completion check.
Native Wiki cache initialization is the existing fully verified environment hook.
"""
from copy import deepcopy
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from .original_goal_binding import binding, fingerprint, require_original_binding, require_local_origin
from .site_navigation_rules import evaluate_navigation, valid_initial_page
from .site_database import select_rows
from .gitlab_native_read_runtime import full_snapshot
from .gitlab_native_csv_probe import protected_snapshot_session, auth_backup, restore_auth_metadata
from .gitlab_directory import (project_reference, directory_access_reference,
                               read_directory_page, directory_checks)
from .gitlab_section import read_section
from .io_utils import atomic_write_json

VERSION = 'gitlab-original-native-navigation-goal-v1'
PROOF_VERSION = 'gitlab-original-native-navigation-twofresh-v1'
KINDS = {'current_settings', 'project_wiki', 'explore_stars'}
SHA = re.compile('[0-9a-f]{64}')
READ = r'''() => {
 const visible=e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const main=document.querySelector('main');
 return {body_page:document.body.getAttribute('data-page'),
   current_user_id:window.gon?.current_user_id??null,
   main_text:main&&visible(main)?main.innerText:null,
   settings_forms:[...document.querySelectorAll('form')].filter(visible).map(f=>({
     action_path:new URL(f.action,location.href).pathname,
     fields:[...f.querySelectorAll('input,select,textarea')].filter(visible).map(e=>e.name).filter(Boolean),
     buttons:[...f.querySelectorAll('button,input[type="submit"]')].filter(visible).map(e=>(e.innerText||e.value||'').trim())
   })).filter(f=>f.action_path==='/-/profile')};
}'''

def enabled(contract):
    if 'gitlab_navigation_goal' not in contract:
        return False
    spec = contract['gitlab_navigation_goal']
    if (contract.get('domain') != 'gitlab' or not isinstance(spec, dict)
            or spec.get('version') != VERSION or spec.get('kind') not in KINDS
            or contract.get('heldout_quarantine') is not False
            or contract.get('eligible_for_training') is not False
            or contract.get('task_text_changed') is not False
            or not isinstance(contract.get('completion'), dict)
            or any(contract.get(k) for k in ('gitlab_native_read','preferences','query','native_csv_export',
                                            'project_creation','fork_creation','ref_creation','repository_download'))):
        raise ValueError('Separate original development native navigation declaration required')
    binding(contract)
    return True

def reference(site, contract, username):
    enabled(contract)
    user = select_rows(site, "SELECT id,username FROM users WHERE username='" + username.replace("'", "''") + "'")
    if len(user) != 1 or type(user[0]['id']) is not int:
        raise ValueError('Unique native task account required')
    kind = contract['gitlab_navigation_goal']['kind']
    result = {'kind': kind, 'account': user[0]}
    if kind == 'project_wiki':
        path = contract['gitlab_navigation_goal']['project_path']
        rows = select_rows(site, "SELECT p.id,r.path,p.name FROM projects p JOIN routes r ON r.source_type='Project' AND r.source_id=p.id WHERE r.path='" + path.replace("'", "''") + "'")
        if len(rows) != 1 or type(rows[0]['id']) is not int:
            raise ValueError('Unique native named project required')
        result['project'] = rows[0]
    elif kind == 'explore_stars':
        result['directory'] = {'kind': 'stars', 'scope': 'explore',
                               'reference': project_reference(site),
                               'access_reference': directory_access_reference(site, username)}
    return result

def read_terminal(page, kind):
    native = page.evaluate(READ)
    native['section'] = read_section(page)
    if kind == 'explore_stars':
        native['directory'] = read_directory_page(page)
    return native

def evaluate(contract, page, private_reference, *, site_origin):
    enabled(contract); require_local_origin(site_origin)
    base = evaluate_navigation(contract, page, site_origin=site_origin)
    base['version'] = VERSION
    if base['status'] != 'success':
        return base
    state = page.get('gitlab_navigation_goal')
    if not isinstance(state, dict) or not isinstance(state.get('body_page'), str):
        return {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': base['checks'],
                'reason': 'Native terminal page identity missing'}
    kind = contract['gitlab_navigation_goal']['kind']
    if private_reference.get('kind') != kind:
        raise ValueError('Independent native reference family differs')
    checks = base['checks'] | {'bound_authenticated_account':
                               state.get('current_user_id') == private_reference['account']['id']}
    if kind == 'current_settings':
        forms = state.get('settings_forms')
        if not isinstance(forms, list):
            return {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': checks,
                    'reason': 'Native settings form capture missing'}
        checks['native_settings_page'] = state['body_page'] == 'profiles:show'
        checks['native_settings_form'] = any(isinstance(f, dict) and f.get('action_path') == '/-/profile'
            and {'user[name]', 'user[email]'} <= set(f.get('fields', []))
            and 'Update profile settings' in f.get('buttons', []) for f in forms)
        text = state.get('main_text')
        checks['visible_settings_content'] = isinstance(text, str) and 'Main settings' in text and 'Full name' in text
    elif kind == 'project_wiki':
        project = private_reference['project']; section = state.get('section')
        if not isinstance(section, dict) or not isinstance(section.get('breadcrumbs'), list):
            return {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': checks,
                    'reason': 'Native named Wiki project identity missing'}
        checks['native_wiki_page'] = state['body_page'] in ('projects:wikis:show', 'projects:wikis:index')
        checks['native_wiki_project'] = (section.get('project_ids') == [str(project['id'])]
            and '/' + project['path'] in {r.get('path', '').rstrip('/') for r in section['breadcrumbs']})
        text = state.get('main_text')
        # Access-only goals accept the real native empty Wiki entry. No claim
        # of available Wiki articles or comprehension is made.
        checks['visible_native_wiki_entry'] = isinstance(text, str) and bool(text.strip()) and section.get('main_id') == 'content-body'
    else:
        try: checks.update(directory_checks(private_reference['directory'], state.get('directory'), page['url']))
        except (ValueError, KeyError, TypeError):
            return {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': checks,
                    'reason': 'Complete native Explore collection capture missing'}
        checks['native_explore_stars'] = state['body_page'] == 'explore:projects:starred'
    passed = all(checks.values())
    return {'version': VERSION, 'status': 'success' if passed else 'failure', 'reward': float(passed),
            'checks': checks, 'reason': None}

def require_initialization(cycle):
    import gitlab_native_wiki_cache_init as cache
    for key in ('native_before_initialization', 'protected_before', 'protected_after'):
        full_snapshot(cycle.get(key))
    record = cache.parse_result('LAB_NATIVE_WIKI_CACHE_INIT_BEGIN\n' + json.dumps(cycle.get('native_initialization_record')) + '\nLAB_NATIVE_WIKI_CACHE_INIT_END\n')
    actual = cache.verify_effects(cycle.get('columns_before'), cycle.get('columns_after'),
        cycle['native_before_initialization'], cycle['protected_before'], record)
    for columns, full in ((cycle['columns_before'], cycle['native_before_initialization']),
                          (cycle['columns_after'], cycle['protected_before'])):
        if columns['columns'] != full['projects']['columns'] or columns['row_count'] != full['projects']['rows']:
            raise ValueError('Complete native column capture differs from full projects coverage')
    if cycle.get('native_initialization_effects') != actual or cycle['protected_before'] != cycle['protected_after']:
        raise ValueError('Exact native initialization and complete unchanged protected state required')

def prepare_reset(site, contract, username, folder):
    """The same bounded environment preparation is used by controls and runner."""
    import gitlab_native_wiki_cache_init as cache
    folder = Path(folder); folder.mkdir(exist_ok=False)
    cold, baseline, effects = cache.initialize(site, folder)
    full_snapshot(cold); full_snapshot(baseline)
    record = json.loads((folder / 'native-cache-initialization.json').read_text())['native_record']
    result = {'native_before_initialization': cold, 'protected_before': baseline,
              'native_initialization_effects': effects, 'native_initialization_record': record,
              'columns_before': json.loads((folder / 'columns-before-native-initialization.json').read_text()),
              'columns_after': json.loads((folder / 'columns-after-native-initialization.json').read_text()),
              'private_reference': reference(site, contract, username)}
    return result, auth_backup(site, username)

def require_admission(contract, proof):
    enabled(contract)
    if (not isinstance(proof, dict) or proof.get('version') != PROOF_VERSION
            or proof.get('contract_fingerprint') != fingerprint(contract)
            or proof.get('original_binding') != binding(contract)
            or proof.get('actor_attempts') != 0 or type(proof.get('actor_attempts')) is not int
            or proof.get('api_calls') != 0 or type(proof.get('api_calls')) is not int
            or proof.get('formal_preinference_lifecycle_verified') is not True):
        raise ValueError('Actual original no-model native navigation lifecycle proof required')
    cycles = proof.get('cycles')
    if not isinstance(cycles, list) or len(cycles) != 2:
        raise ValueError('Two independent fresh native reset cycles required')
    ids = [row.get('fresh_instance_id') for row in cycles]
    if any(not isinstance(x, str) or not SHA.fullmatch(x) for x in ids) or len(set(ids)) != 2:
        raise ValueError('Two distinct native instances required')
    for cycle in cycles:
        require_initialization(cycle)
        cases = cycle.get('controls'); expected = {'initial_no_op', 'positive', 'wrong_target', 'wrong_secondary', '404', 'login'}
        if not isinstance(cases, dict) or set(cases) != expected:
            raise ValueError('Actual positive, both wrong targets, no-op, 404 and login controls required')
        for name, control in cases.items():
            if name in ('initial_no_op', 'wrong_target', 'wrong_secondary') and not valid_initial_page(control['page'], site_origin=control['site_origin']):
                raise ValueError('Original first start or actual wrong native target is not valid')
            status = evaluate(contract, control['page'], cycle['private_reference'], site_origin=control['site_origin'])['status']
            if status != ('success' if name == 'positive' else 'failure'):
                raise ValueError('Native navigation control result differs: ' + name)
        if cycle.get('private_reference_after') != cycle.get('private_reference'):
            raise ValueError('Independent native reference changed')
    for key in ('native_before_initialization', 'protected_before', 'native_initialization_effects', 'private_reference'):
        if cycles[0][key] != cycles[1][key]:
            raise ValueError('Independent native reset/reference differs: ' + key)
    return deepcopy(cycles[0]['private_reference'])

class NavigationGoalHooks:
    def __init__(self, contract, proof, directory):
        self.reference = require_admission(contract, proof)
        self.contract, self.proof, self.directory = deepcopy(contract), deepcopy(proof), Path(directory)
        self.prepared = self.scored = False
        self.context = self.initial_page = None

    def prepare(self, site, username):
        if self.prepared: raise ValueError('One verified reset per original task required')
        actual, auth = prepare_reset(site, self.contract, username, self.directory / 'native-navigation-initialization')
        expected = self.proof['cycles'][0]
        if any(actual[k] != expected[k] for k in ('native_before_initialization', 'protected_before',
               'native_initialization_effects', 'private_reference')):
            raise ValueError('Actual full native reset/reference differs from CPU proof')
        self.site, self.username, self.before, self.auth = site, username, actual['protected_before'], auth
        self.prepared = True

    def attach(self, context):
        if not self.prepared or self.context is not None: raise ValueError('One prepared original browser context required')
        self.context = context

    def observe_initial(self, page):
        if self.initial_page is not None or page.context is not self.context: raise ValueError('One bound original initial page required')
        self.initial_page = page

    def capture_terminal(self, page, terminal):
        if page.context is not self.context or self.initial_page is None: raise ValueError('Bound original terminal page required')
        terminal['gitlab_navigation_goal'] = read_terminal(page, self.contract['gitlab_navigation_goal']['kind'])
        atomic_write_json(self.directory / 'terminal-native-navigation.json', terminal)

    def score_terminal(self, site, page, *, runtime_error=None):
        if not self.prepared or self.scored or site is not self.site: raise ValueError('One final judgment after verified reset required')
        self.scored = True; errors = []; after = ref = None
        try:
            restore_auth_metadata(site, self.auth)
            after = protected_snapshot_session(site, self.directory / 'native-navigation-protected-progress.jsonl')
            full_snapshot(after); ref = reference(site, self.contract, self.username)
        except Exception as error: errors.append({'exception_type': type(error).__name__})
        integrity = not errors and after == self.before and ref == self.reference
        atomic_write_json(self.directory / 'native-navigation-full16-protection.json',
                          {'before': self.before, 'after': after, 'unchanged': integrity, 'errors': errors, 'complete16': True, 'columns_ignored': []})
        if runtime_error or errors:
            return {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': {}, 'reason': 'Native runtime or full reference incomplete'}, integrity
        judgment = evaluate(self.contract, page, self.reference, site_origin=site.url)
        judgment['checks']['complete_native_state_unchanged'] = integrity
        if judgment['status'] != 'unknown' and not integrity: judgment.update(status='failure', reward=0.0)
        return judgment, integrity

    def close(self):
        pass

def feedback(judgment):
    meanings = {'bound_authenticated_account': 'The terminal native page belongs to the task account.',
                'native_settings_page': 'The terminal page is the native account settings page.',
                'native_settings_form': 'The real editable account settings form is displayed.',
                'visible_settings_content': 'Account settings content is visibly rendered.',
                'native_wiki_page': 'The native project Wiki entry is displayed.',
                'native_wiki_project': 'The Wiki belongs to the requested project.',
                'visible_native_wiki_entry': 'The real Wiki content or native empty entry is visible.',
                'native_explore_stars': 'The native Explore stars collection is displayed.',
                'complete_native_state_unchanged': 'All declared native records remain unchanged.'}
    return {'status': judgment.get('status'), 'reward': judgment.get('reward'),
            'checks': [{'name': k, 'passed': v, 'condition': meanings.get(k, k)} for k, v in judgment.get('checks', {}).items()],
            'action_sequence_provided': False}
