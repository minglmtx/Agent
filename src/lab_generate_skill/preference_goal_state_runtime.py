"""Allow genuinely satisfied native Boolean state goals without changing reset.

This optional lifecycle is for already-satisfied state goals. The existing
change-required preference protocol remains available for other task families.
All thirteen declared native tables are still protected at termination.
"""
from copy import deepcopy
from pathlib import Path
import re
from .original_goal_binding import binding, fingerprint, require_original_binding, require_local_origin
from .site_preferences_rules import FIELDS, preference_state, evaluate_preferences, preferences_feedback, valid_choices
from .site_navigation_rules import valid_initial_page
from .reddit_native_read_protection import complete_snapshot
from .reddit_native_read_runtime import validate_complete_snapshot
from .io_utils import atomic_write_json

VERSION = 'preference-original-already-satisfied-goal-v1'
PROOF_VERSION = 'preference-original-goal-state-full13-twofresh-v1'
SHA = re.compile('[0-9a-f]{64}')
CONTROLS = {'no_op': 'success', 'saved_wrong_target': 'failure', 'unsaved_target': 'failure',
            'wrong_setting': 'failure', 'positive': 'success', '404': 'failure', 'login': 'failure'}

def enabled(contract):
    if 'preference_goal_state' not in contract:
        return False
    spec = contract['preference_goal_state']; settings = contract.get('preferences')
    if (contract.get('domain') != 'reddit' or not isinstance(spec, dict)
            or spec != {'version': VERSION, 'initial_goal_status': 'success'}
            or not isinstance(settings, dict) or settings.get('mode', 'targets') != 'targets'
            or not isinstance(settings.get('username'), str) or not settings['username']
            or not isinstance(settings.get('targets'), dict) or not settings['targets']
            or any(k not in FIELDS or type(v) is not bool for k, v in settings['targets'].items())
            or contract.get('heldout_quarantine') is not False
            or contract.get('eligible_for_training') is not False
            or contract.get('task_text_changed') is not False
            or any(contract.get(k) for k in ('gitlab_native_read','reddit_native_read','membership','query','submission','wiki'))):
        raise ValueError('Explicit original already-satisfied Boolean state goal required')
    binding(contract)
    return True

def validate_state(state, contract):
    targets = contract['preferences']['targets']
    if (not isinstance(state, dict) or set(state) != {'user_id', 'username', 'values'}
            or type(state['user_id']) is not int or state['user_id'] <= 0
            or state['username'] != contract['preferences']['username']
            or not isinstance(state['values'], dict) or set(state['values']) != set(FIELDS)
            or any(type(state['values'].get(k)) is not bool for k in targets)):
        raise ValueError('Complete original account preference reference required')
    return state

def initially_satisfied(contract, state):
    enabled(contract); validate_state(state, contract)
    return all(state['values'][k] == value for k, value in contract['preferences']['targets'].items())

def evaluate(contract, page, initial, final, *, site_origin, runtime_error=None):
    enabled(contract); validate_state(initial, contract); require_local_origin(site_origin)
    if not initially_satisfied(contract, initial):
        raise ValueError('Already-satisfied lifecycle cannot revise an unsatisfied original reset')
    result = evaluate_preferences(contract, page, initial, final,
                                  site_origin=site_origin, runtime_error=runtime_error)
    result['version'] = VERSION
    return result

def validate_submission(value, username, site_origin):
    if (not isinstance(value, dict) or value.get('overflow') is not False
            or not isinstance(value.get('native_posts'), list) or not value['native_posts']
            or not isinstance(value.get('trusted_clicks'), list)):
        raise ValueError('Actual native trusted preference submission required')
    from urllib.parse import quote
    path = '/user/' + quote(username, safe='') + '/preferences'
    if any(row != {'method': 'POST', 'path': path} for row in value['native_posts']):
        raise ValueError('Unexpected native preference submission route')
    if not any(event.get('trusted') is True and event.get('control', {}).get('effective_method') == 'post'
            and (event['control'].get('effective_action') or {}).get('path') == path
            and (event['control'].get('effective_action') or {}).get('origin') == site_origin
            for event in value['trusted_clicks']):
        raise ValueError('Bound original native submit control required')

def require_admission(contract, proof):
    enabled(contract)
    if (not isinstance(proof, dict) or proof.get('version') != PROOF_VERSION
            or proof.get('contract_fingerprint') != fingerprint(contract)
            or proof.get('original_binding') != binding(contract)
            or proof.get('actor_attempts') != 0 or type(proof.get('actor_attempts')) is not int
            or proof.get('api_calls') != 0 or type(proof.get('api_calls')) is not int
            or proof.get('formal_preinference_lifecycle_verified') is not True):
        raise ValueError('Actual original no-model state-goal lifecycle proof required')
    cycles = proof.get('cycles')
    if not isinstance(cycles, list) or len(cycles) != 2:
        raise ValueError('Two independently reset state-goal cycles required')
    ids = [c.get('fresh_instance_id') for c in cycles]
    if any(not isinstance(x, str) or not SHA.fullmatch(x) for x in ids) or len(set(ids)) != 2:
        raise ValueError('Two distinct original native instances required')
    for cycle in cycles:
        for k in ('protected_before', 'protected_after'):
            validate_complete_snapshot(cycle.get(k))
        before = validate_state(cycle.get('initial_state'), contract)
        if (not initially_satisfied(contract, before) or cycle.get('initial_goal_status') != 'success'
                or cycle.get('final_state') != before or cycle['protected_before'] != cycle['protected_after']
                or cycle.get('native_form_choices_verified') is not True
                or not valid_choices(before['values'], cycle.get('native_choices', {}))
                or any(cycle['native_choices'][key] != {'type': 'boolean'} for key in contract['preferences']['targets'])):
            raise ValueError('Unchanged original satisfied reset and complete13 restoration required')
        controls = cycle.get('controls')
        if not isinstance(controls, dict) or set(controls) != set(CONTROLS):
            raise ValueError('All actual saved, unsaved, wrong-setting and error controls required')
        for name, control in controls.items():
            if control.get('initial_state') != before:
                raise ValueError('Control changed the original goal baseline')
            validate_state(control.get('final_state'), contract)
            if name == 'no_op' and not valid_initial_page(control['page'], site_origin=control['site_origin']):
                raise ValueError('Recorded original first start invalid')
            status = evaluate(contract, control['page'], before, control['final_state'], site_origin=control['site_origin'])['status']
            if status != CONTROLS[name]:
                raise ValueError('Measured actual state-goal control differs: ' + name)
            final = control['final_state']; targets = contract['preferences']['targets']
            changed = {key for key in FIELDS if final['values'][key] != before['values'][key]}
            if name == 'saved_wrong_target':
                if changed != set(targets) or any(final['values'][key] == target for key, target in targets.items()):
                    raise ValueError('Saved wrong-target control must change exactly the target Boolean values')
            if name in ('saved_wrong_target', 'positive', 'wrong_setting'):
                validate_submission(control.get('native_submission'), contract['preferences']['username'], control['site_origin'])
            if name == 'positive' and final != before:
                raise ValueError('Positive target must retain the unchanged original account state')
            if name == 'wrong_setting' and (len(changed) != 1 or changed & set(targets)):
                raise ValueError('Wrong-setting control must change precisely one unrelated preference')
            if name == 'unsaved_target':
                if control.get('unsaved_ui_values') != contract['preferences']['targets']:
                    raise ValueError('Native unsaved controls were not actually edited to target')
                if all(control['final_state']['values'][k] == v for k, v in contract['preferences']['targets'].items()):
                    raise ValueError('Unsaved negative must have an actually wrong saved target')
                if final != controls['saved_wrong_target']['final_state']:
                    raise ValueError('Unsaved UI edits must not change saved native state')
        if cycle.get('native_mutations_verified') is not True:
            raise ValueError('Actual native settings submissions and full restoration required')
        validate_submission(cycle.get('restoration_native_submission'), contract['preferences']['username'],
                            controls['positive']['site_origin'])
    for key in ('initial_state', 'protected_before'):
        if cycles[0][key] != cycles[1][key]:
            raise ValueError('Independent original cold state differs: ' + key)
    return deepcopy(cycles[0]['initial_state'])

class PreferenceGoalStateHooks:
    def __init__(self, contract, proof, directory):
        self.initial = require_admission(contract, proof)
        self.contract, self.proof, self.directory = deepcopy(contract), deepcopy(proof), Path(directory)
        self.prepared = self.scored = False
        self.context = self.initial_page = None

    def prepare(self, site, username):
        if self.prepared or username != self.contract['preferences']['username']:
            raise ValueError('One original target account reset required')
        before = complete_snapshot(site, self.directory / 'goal-state-protected-before-progress.jsonl')
        validate_complete_snapshot(before)
        measured = preference_state(site, username)
        if (before != self.proof['cycles'][0]['protected_before'] or measured != self.initial
                or not initially_satisfied(self.contract, measured)):
            raise ValueError('Actual full original goal state differs from CPU proof')
        self.site, self.username, self.before = site, username, before
        self.prepared = True

    def attach(self, context):
        if not self.prepared or self.context is not None: raise ValueError('One prepared original browser context required')
        self.context = context

    def observe_initial(self, page):
        if self.initial_page is not None or page.context is not self.context: raise ValueError('One bound original initial page required')
        self.initial_page = page

    def capture_terminal(self, page, terminal):
        if page.context is not self.context or self.initial_page is None: raise ValueError('Bound original terminal page required')
        # No UI action or completion hint is generated here.
        terminal['preference_goal_state_terminal'] = {'captured_after_termination': True}

    def score_terminal(self, site, page, *, runtime_error=None):
        if not self.prepared or self.scored or site is not self.site: raise ValueError('One final judgment after original reset required')
        self.scored = True; errors = []; after = final = None
        try:
            final = preference_state(site, self.username)
            after = complete_snapshot(site, self.directory / 'goal-state-protected-after-progress.jsonl')
            validate_complete_snapshot(after)
        except Exception as error: errors.append({'exception_type': type(error).__name__})
        integrity = not errors and after == self.before
        atomic_write_json(self.directory / 'goal-state-complete13-protection.json',
                          {'before': self.before, 'after': after, 'unchanged': integrity, 'errors': errors,
                           'complete13': True, 'users_only_ignored_column': 'last_seen'})
        if errors:
            return {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': {},
                    'reason': 'Complete native state or account reference unavailable'}, integrity
        result = evaluate(self.contract, page, self.initial, final, site_origin=site.url, runtime_error=runtime_error)
        result['checks']['complete_native_state_unchanged'] = integrity
        if result['status'] != 'unknown' and not integrity: result.update(status='failure', reward=0.0)
        return result, integrity

    def close(self):
        pass

def feedback(judgment):
    copy = deepcopy(judgment)
    integrity = copy['checks'].pop('complete_native_state_unchanged', None)
    result = preferences_feedback(copy)
    if integrity is not None:
        result['checks'].append({'name': 'complete_native_state_unchanged', 'passed': integrity,
                                'condition': 'All thirteen declared native records retain their original saved state.'})
    return result
