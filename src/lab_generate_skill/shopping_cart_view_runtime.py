"""Read-only cart-view lifecycle shared by controls and the online runner.

Completion depends on the complete native cart surface at termination, not a
particular navigation path. Private cart contents never enter actor feedback.
"""
from copy import deepcopy
from pathlib import Path
import re

from . import shopping_cart_view as rule
from .site_cart_rules import cart_state
from .original_goal_binding import binding, fingerprint, require_original_binding, require_local_origin
from .io_utils import atomic_write_json

VERSION = 'shopping-cart-view-normal-runtime-v1'
PROOF_VERSION = 'shopping-cart-view-two-cold-controls-v1'
CONTROL_STATUSES = {'minicart': 'success', 'full_cart': 'success', 'closed': 'failure',
                    'wrong_object': 'failure', '404': 'failure', 'login': 'failure'}


def enabled(contract):
    if 'shopping_cart_view' not in contract:
        return False
    if (contract.get('domain') != 'shopping'
            or contract['shopping_cart_view'] != {'version': VERSION, 'kind': 'complete_cart_contents'}
            or contract.get('heldout_quarantine') is not False
            or contract.get('eligible_for_training') is not False
            or contract.get('task_text_changed') is not False
            or contract.get('task_id') != contract.get('source_task_id')
            or contract.get('completion')
            or any(contract.get(k) for k in ('cart', 'search', 'query', 'checkout', 'order',
                    'shopping_offline_training', 'shopping_complete_query', 'shopping_native_three'))):
        raise ValueError('Separate unchanged read-only cart-view contract required')
    binding(contract)
    return True


def fields(contract):
    enabled(contract)
    return []


def public_goal(contract):
    enabled(contract)
    return contract['goal']


def require_controls(contract, proof):
    """Re-score actual native control captures; summary booleans are insufficient."""
    enabled(contract)
    if (proof.get('version') != PROOF_VERSION
            or proof.get('contract_fingerprint') != fingerprint(contract)
            or proof.get('source_binding') != binding(contract)
            or proof.get('actor_attempts') != 0 or proof.get('api_calls') != 0
            or not re.fullmatch('[0-9a-f]{64}', proof.get('source_archive_sha256', ''))):
        raise ValueError('Bound no-model native controls required')
    cycles = proof.get('cycles', [])
    if len(cycles) != 2 or [c.get('cycle') for c in cycles] != [0, 1]:
        raise ValueError('Two independent cold control cycles required')
    for cycle in cycles:
        require_local_origin(cycle['site_origin'])
        if (not re.fullmatch('[0-9a-f]{64}', cycle.get('initial_fingerprint', ''))
                or cycle['initial_fingerprint'] != cycle.get('final_fingerprint')
                or cycle['initial_cart'] != cycle.get('final_cart')
                or set(cycle.get('controls', {})) != set(CONTROL_STATUSES)):
            raise ValueError('Complete unchanged native cart and reset controls required')
        for name, expected in CONTROL_STATUSES.items():
            capture = cycle['controls'][name]
            verdict = rule.evaluate(capture['page'], capture['view'], cycle['initial_cart'],
                                    cycle['final_cart'], site_origin=cycle['site_origin'])
            if verdict['status'] != expected:
                raise ValueError('Native cart control mismatch: ' + name)
            if name == 'login' and capture['page'].get('login_page') is not True:
                raise ValueError('Actual unauthenticated login control required')
    if any(cycles[0][key] != cycles[1][key] for key in ('initial_fingerprint', 'initial_cart')):
        raise ValueError('Independent cold native baselines differ')
    return deepcopy(cycles[0]['initial_cart'])


def require_admission(contract, proof):
    reference = require_controls(contract, proof)
    lifecycle = proof.get('normal_lifecycle', {})
    # Native surface tests alone do not prove runner initialization/capture.
    if lifecycle.get('version') != VERSION or len(lifecycle.get('cycles', [])) != 2:
        raise ValueError('Normal BrowserGym lifecycle validation is still required')
    for index, cycle in enumerate(lifecycle['cycles']):
        if (cycle.get('cycle') != index or cycle.get('initial_fingerprint') != proof['cycles'][index]['initial_fingerprint']
                or cycle.get('final_fingerprint') != cycle.get('initial_fingerprint')
                or cycle.get('statuses') != CONTROL_STATUSES
                or cycle.get('private_feedback_clean') is not True
                or cycle.get('initial_start_preserved') is not True
                or cycle.get('all_terminal_integrity') is not True):
            raise ValueError('Incomplete normal cart-view lifecycle controls')
    return reference


class CartViewHooks:
    def __init__(self, contract, proof, directory):
        # Runner calls require_admission before construction. CPU probes use
        # this same hook to establish that final lifecycle evidence.
        self.reference = require_controls(contract, proof)
        self.contract, self.proof = deepcopy(contract), deepcopy(proof)
        self.directory = Path(directory)
        self.site = self.context = self.initial_page = None
        self.prepared = self.scored = False

    def prepare(self, site, username):
        if self.prepared:
            raise ValueError('Cart-view hook cannot be reused across episodes')
        self.site, self.username = site, username
        self.before = site.fingerprint()
        if (self.before != self.proof['cycles'][0]['initial_fingerprint']
                or cart_state(site, username) != self.reference):
            raise ValueError('Actual native cart/reset differs from independent controls')
        self.prepared = True

    def attach(self, context):
        if not self.prepared or self.context is not None:
            raise ValueError('One prepared browser context required')
        self.context = context

    def observe_initial(self, page):
        if page.context is not self.context or self.initial_page is not None:
            raise ValueError('One original initial page required')
        self.initial_page = page

    def capture_terminal(self, page, terminal):
        if page.context is not self.context or self.initial_page is None:
            raise ValueError('Bound terminal page required')
        terminal['shopping_cart_view'] = rule.read(page)
        atomic_write_json(self.directory / 'terminal-cart-view.json', terminal)

    def score_terminal(self, site, terminal, *, runtime_error=None):
        if not self.prepared or self.scored or site is not self.site:
            raise ValueError('One final score on the prepared site required')
        self.scored = True
        after = final = None
        error = None
        try:
            after = site.fingerprint()
            final = cart_state(site, self.username)
        except Exception as exc:
            error = type(exc).__name__
        integrity = error is None and after == self.before and final == self.reference
        atomic_write_json(self.directory / 'cart-view-private-integrity.json', {
            'before': self.before, 'after': after, 'initial_cart': self.reference,
            'final_cart': final, 'unchanged': integrity, 'error_type': error})
        if runtime_error or not integrity:
            return {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': {},
                    'reason': 'Runtime or independent state verification incomplete'}, integrity
        result = rule.evaluate(terminal, (terminal or {}).get('shopping_cart_view'),
                               self.reference, final, site_origin=site.url)
        result['version'] = VERSION
        return result, integrity

    def close(self):
        pass


def feedback(judgment):
    labels = {'page_valid': 'The final page is a valid local task page.',
              'cart_reference_unchanged': 'The task account cart was preserved.',
              'complete_cart_items_displayed': 'The final visible cart contains all current items.'}
    return {'status': judgment.get('status'), 'checks': [
        {'condition': labels[k], 'passed': bool(v)}
        for k, v in judgment.get('checks', {}).items() if k in labels]}
