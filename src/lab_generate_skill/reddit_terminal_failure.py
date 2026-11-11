"""Preserve independently established goal failure after a complete native guard.

The delivered reading/RSS hooks retain their original source-bound admission
and native protection. This adapter only reconciles their legacy final merge,
which replaced even a verified goal failure with unknown on extra writes.
"""
from copy import deepcopy
import hashlib
import json

from .io_utils import atomic_write_json
from .site_result_guard import guard_site_result
from .reddit_native_read_runtime import validate_complete_snapshot

VERSION = 'reddit-independent-terminal-failure-v1'
REASONS = {
    'reddit_local_read_hooks': 'Runtime/full13/full sidecar protection mismatch',
    'reddit_rss_subscription_hooks': 'Runtime/native13/sidecar integrity mismatch',
}


def reconcile(module, contract, reference, receipt, judgment, *, runtime_error=None):
    """Pure replay of the same evaluator; never infer success or missing data."""
    original = deepcopy(judgment)
    if (runtime_error or module.__name__ not in REASONS
            or original.get('status') != 'unknown'
            or original.get('reason') != REASONS[module.__name__]):
        return original
    if (receipt.get('integrity') is not False or receipt.get('judgment') != judgment
            or receipt.get('provenance') != module.provenance()
            or receipt.get('guard_scope') != 'normal_source_full13_before_after'
            or not receipt.get('lifecycle') or receipt['lifecycle'][-1] != 'score_terminal'):
        raise ValueError('Completed same-hook protection receipt required')
    validate_complete_snapshot(receipt['actual_complete13_before'])
    validate_complete_snapshot(receipt['actual_complete13_after'])
    args = [contract, reference, receipt['observations'], receipt['terminal']]
    if module.__name__ == 'reddit_rss_subscription_hooks':
        if reference != receipt['private_reference']:
            raise ValueError('Bound RSS reference differs')
        args.extend([receipt['actual_sidecar_before'], receipt['actual_sidecar_after'],
                     receipt['native_feed_receipts']])
        independent, _ = module.evaluate(*args, site_origin=receipt['site_origin'])
    else:
        independent = module.evaluate(*args, site_origin=receipt['site_origin'])
    checks = independent.get('checks')
    if (independent.get('status') != 'failure' or independent.get('reward') != 0.0
            or not isinstance(checks, dict) or not checks
            or any(type(v) is not bool for v in checks.values()) or all(checks.values())):
        return original
    corrected = guard_site_result(independent, runtime_error=None, selected_records_unchanged=False)
    corrected['terminal_guard_revision'] = VERSION
    return corrected


class TerminalFailureHooks:
    def __init__(self, hooks, module):
        self._hooks = hooks
        self._module = module

    def __getattr__(self, name):
        return getattr(self._hooks, name)

    def score_terminal(self, site, terminal, *, runtime_error=None):
        judgment, integrity = self._hooks.score_terminal(site, terminal, runtime_error=runtime_error)
        receipt = getattr(self._hooks, 'receipt', {})
        reference = (receipt.get('private_reference') if self._module.__name__ == 'reddit_rss_subscription_hooks'
                     else self._hooks.expected)
        corrected = reconcile(self._module, self._hooks.contract, reference, receipt,
                              judgment, runtime_error=runtime_error)
        if corrected != judgment:
            # Original full receipt stays intact; this small record explains the
            # only difference between its legacy judgment and the final result.
            receipt_sha = hashlib.sha256(json.dumps(receipt, sort_keys=True, ensure_ascii=False,
                                                    separators=(',', ':')).encode()).hexdigest()
            atomic_write_json(self._hooks.directory / 'terminal-failure-reconciliation.json', {
                'version': VERSION, 'original_receipt_canonical_sha256': receipt_sha,
                'original_judgment': judgment, 'evaluation': corrected,
                'selected_records_unchanged': integrity, 'success_promoted': False,
                'training_admitted': False})
        return corrected, integrity


def wrap(hooks, module):
    return TerminalFailureHooks(hooks, module) if module.__name__ in REASONS else hooks
