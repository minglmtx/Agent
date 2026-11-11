"""Explicit public-goal revisions over unchanged native completion contracts.

The original contract and full control proof remain immutable. Only reviewed
public wording is replaced; initialization, native capture, references and
protection are delegated to the original implementation. This grants neither
a retry lease nor training admission.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from . import reddit_native_read_runtime as reddit
from . import shopping_native_three_runtime as shopping
from .io_utils import atomic_write_json
from .source_revision_binding import binding, fingerprint, require_source_binding, local_path

VERSION = 'reviewed-public-completion-runtime-v1'
PROOF_VERSION = 'reviewed-public-completion-proof-v1'
FEEDBACK_VERSIONS = (VERSION,)
# The delegated Shopping guard allows only native comparison rows to change.
# Reddit's delegated full guard additionally enforces its selected-state hash.
AUTHORIZED_TARGET_WRITES = True


def _plain(value):
    return {k: deepcopy(v) for k, v in value.items() if k != 'admission_result'}


def _family(original):
    if original.get('domain') == 'reddit' and original.get('reddit_native_read', {}).get('kind') == 'formatting_help':
        reddit.enabled(original)
        return reddit
    if original.get('domain') == 'shopping' and shopping.enabled(original):
        if shopping.validate(original)['kind'] == 'guest_compare':
            return shopping
    raise ValueError('No reviewed public-completion adapter for this native family')


def _expected(original, task_id, goal, urls, review_pin):
    module = _family(original)
    value = _plain(original)
    value.pop('reddit_native_read', None)
    value['completion'] = {}
    value.update(task_id=task_id, goal=goal, original_goal=original['goal'],
                 task_text_changed=True, recorded_start_urls=deepcopy(urls),
                 goal_revision={'version': VERSION, 'original_goal': original['goal'],
                     'derived_goal': goal,
                     'reason': 'Make the reviewed terminal completion scope explicit in the public task.',
                     'equivalent_to_original_evaluation': False},
                 public_completion={'version': VERSION, 'original_contract': _plain(original),
                                    'scope_review': deepcopy(review_pin)})
    if module is reddit:
        value.pop('runtime_version', None)
    return value


def make_contract(original, inventory, review_pin, *, goal, task_id):
    original = _plain(original)
    if (inventory.get('task_id') != original.get('source_task_id')
            or inventory.get('goal') != original['goal']
            or inventory.get('domain') != original['domain']
            or inventory.get('source_trace_ids') != original['source_trace_ids']
            or inventory.get('heldout_quarantine') is not False
            or list(map(local_path, inventory.get('recorded_start_urls', []))) != original['recorded_start_paths']):
        raise ValueError('Authoritative original source, starts, traces and split required')
    candidate = _expected(original, task_id, goal, inventory['recorded_start_urls'], review_pin)
    enabled(candidate)
    _review(candidate)
    return candidate


def enabled(contract):
    if 'public_completion' not in contract:
        return False
    spec = contract['public_completion']
    if not isinstance(spec, dict) or set(spec) != {'version', 'original_contract', 'scope_review'} or spec['version'] != VERSION:
        raise ValueError('Explicit original contract and reviewed public scope required')
    original = spec['original_contract']
    if not isinstance(original, dict) or 'public_completion' in original or 'admission_result' in original:
        raise ValueError('One immutable original native contract required')
    expected = _expected(original, contract.get('task_id'), contract.get('goal'),
                         contract.get('recorded_start_urls'), spec['scope_review'])
    if (_plain(contract) != expected or contract.get('task_id') == original['task_id']
            or not isinstance(contract.get('task_id'), str) or not contract['task_id'].strip()
            or contract.get('goal') == original['goal']
            or contract.get('eligible_for_training') is not False
            or any(contract.get(k) is True for k in ('training_admitted', 'normal_gate_passed'))):
        raise ValueError('Revision may change only reviewed public wording and its explicit mapping')
    binding(contract)
    if contract['start_path'] != original['start_path']:
        raise ValueError('Public completion revision must preserve the original start')
    return True


def _pinned(pin):
    if not isinstance(pin, dict) or set(pin) != {'path', 'sha256'}:
        raise ValueError('Exact evidence path and hash required')
    path = Path(pin['path'])
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise ValueError('Regular absolute evidence file required')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != pin['sha256']:
        raise ValueError('Retained evidence changed')
    return json.loads(data)


def _review(contract):
    spec = contract['public_completion']
    report = _pinned(spec['scope_review'])
    rows = [r for r in report['records'] if r['source_task_id'] == contract['source_task_id']]
    if len(rows) != 1:
        raise ValueError('One independently reviewed source scope required')
    row = rows[0]
    if (row.get('task_contract') != spec['original_contract']
            or row.get('proposed_public_goal') != contract['goal']
            or row.get('start_path') != contract['start_path']
            or row.get('actual_prompt_and_trajectory_read') is not True
            or row.get('new_actor_required_for_definition') is not True
            or row.get('original_benchmark_equivalence_claimed') is not False):
        raise ValueError('Revision does not match the reviewed original evidence and public goal')


def require_original_binding(contract, original, inventory):
    enabled(contract)
    return require_source_binding(contract, original, inventory, domain=contract['domain'])


def require_admission(contract, proof):
    enabled(contract)
    _review(contract)
    original = contract['public_completion']['original_contract']
    module = _family(original)
    if (proof.get('version') != PROOF_VERSION
            or proof.get('candidate_fingerprint') != fingerprint(contract)
            or proof.get('original_fingerprint') != fingerprint(original)
            or proof.get('runtime_sha256') != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            or proof.get('native_runtime_sha256') != hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
            or proof.get('actor_attempts') != 0 or type(proof.get('actor_attempts')) is not int
            or proof.get('training_admitted') is not False
            or proof.get('api_calls') != 0 or type(proof.get('api_calls')) is not int):
        raise ValueError('Exact candidate and current native runtime qualification required')
    retained = _pinned(proof['original_proof'])
    # Do not rewrite original fingerprints or label the new goal unchanged.
    module.require_admission(deepcopy(original), retained)
    return retained


def make_proof(contract, original_proof_pin):
    enabled(contract)
    original = contract['public_completion']['original_contract']
    module = _family(original)
    proof = {'version': PROOF_VERSION, 'candidate_fingerprint': fingerprint(contract),
             'original_fingerprint': fingerprint(original),
             'runtime_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'native_runtime_sha256': hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest(),
             'original_proof': deepcopy(original_proof_pin),
             'actor_attempts': 0, 'training_admitted': False, 'api_calls': 0}
    require_admission(contract, proof)
    return proof


def public_goal(contract):
    enabled(contract)
    return contract['goal']


def fields(contract):
    enabled(contract)
    return []


def guest_session(contract):
    enabled(contract)
    return _family(contract['public_completion']['original_contract']) is shopping


def feedback(judgment):
    return {'status': judgment.get('status'), 'reward': judgment.get('reward'),
            'checks': {k: v for k, v in judgment.get('checks', {}).items() if type(v) is bool},
            'private_reference_values_provided': False, 'action_sequence_provided': False}


class NativeReadHooks:
    """Use the original lifecycle and terminal predicate; never choose actions."""
    def __init__(self, contract, proof, directory):
        retained = require_admission(contract, proof)
        self.contract = deepcopy(contract)
        self.original = deepcopy(contract['public_completion']['original_contract'])
        self.directory = Path(directory)
        self.module = _family(self.original)
        self.delegate = (reddit.RedditNativeReadHooks(self.original, retained, directory)
                         if self.module is reddit else shopping.NativeThreeHooks(self.original, retained, directory))
        self.expected_protected = (deepcopy(retained['cycles'][0]['before_protected'])
                                   if self.module is shopping else None)
        self.expected_selected = (retained['cycles'][0]['initial_fingerprint']
                                  if self.module is shopping else None)
        self.site = None
        self.context = None
        self.captured = None
        self.scored = False

    def prepare(self, site, username):
        if self.site is not None or site.domain != self.contract['domain']:
            raise ValueError('One original native site instance required')
        self.site = site
        self.auth = {'username': username}
        if self.module is reddit:
            self.delegate.prepare(site, username)
        else:
            self.delegate.verify_baseline(site, self.auth)
            # NativeThree verifies the reference but not its protected baseline
            # against the cold proof; bind it explicitly before model inference.
            # The original proof is retained on disk, not copied into results.
            if self.delegate.protected_before != self.expected_protected:
                raise RuntimeError('Complete native protected reset differs from controls')
            if site.fingerprint() != self.expected_selected:
                raise RuntimeError('Original selected reset differs from controls')

    def attach(self, context):
        if self.site is None or self.context is not None:
            raise ValueError('One prepared browser context required')
        self.context = context
        if self.module is reddit:
            self.delegate.attach(context)
        else:
            self.delegate.attach(context, self.site.url)

    def observe_initial(self, page):
        if page.context is not self.context:
            raise ValueError('Original browser context required')
        self.delegate.observe_initial(page)

    def capture_terminal(self, page, terminal):
        if self.scored or self.captured is not None or page.context is not self.context or terminal.get('url') != page.url:
            raise ValueError('One bound terminal capture required')
        if self.module is reddit:
            self.delegate.capture_terminal(page, terminal)
        else:
            terminal['shopping_native_three'] = self.delegate.terminal(self.site, page, self.auth)
            atomic_write_json(self.directory/'terminal-shopping-native-three-private.json', terminal['shopping_native_three'])
        self.captured = deepcopy(terminal)

    def score_terminal(self, site, terminal, *, runtime_error=None):
        if site is not self.site or self.scored:
            raise ValueError('One terminal score on the original instance required')
        self.scored = True
        if self.module is reddit:
            result, integrity = self.delegate.score_terminal(site, terminal, runtime_error=runtime_error)
        else:
            if self.captured is None or terminal != self.captured or runtime_error:
                result, integrity = {'status': 'unknown', 'reward': None, 'checks': {}}, False
            else:
                result = self.delegate.evaluate(site, terminal, terminal.get('shopping_native_three'))
                protected_after = shopping.protected_state(site, self.delegate.spec)
                reference_after = shopping.reference(site, self.original, self.auth)
                integrity = (protected_after == self.delegate.protected_before
                             and reference_after == self.delegate.expected)
                atomic_write_json(self.directory/'public-completion-native-protection.json', {
                    'before': self.delegate.protected_before, 'after': protected_after,
                    'initial_selected_sha256': self.expected_selected,
                    'reference_unchanged': reference_after == self.delegate.expected})
                if not integrity and result['status'] != 'unknown':
                    result = dict(result, status='failure', reward=0.0)
        result = dict(result, native_version=result.get('version'), version=VERSION)
        atomic_write_json(self.directory/'public-completion-receipt.json', {
            'task_id': self.contract['task_id'], 'source_task_id': self.contract['source_task_id'],
            'public_goal': self.contract['goal'], 'original_fingerprint': fingerprint(self.original),
            'evaluation': result, 'integrity': integrity})
        return result, integrity

    def close(self):
        self.delegate.close()
