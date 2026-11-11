"""Recognize the single documented Metrics controller-name correction.

Callers must first verify the immutable original control files, task binding,
full native state, reset and cleanup. The current evaluator independently
computes `current` from that same terminal evidence. Original files are never
rewritten, and no other failed or unknown result may be promoted here.
"""
from copy import deepcopy

VERSION = 'metrics-dashboard-controller-correction-v1'
CHECKS = frozenset(('valid_native_page', 'bound_native_account',
    'native_main_content', 'bound_target_project', 'requested_native_section',
    'native_section_identity'))


def recorded_verdict_matches(recorded, current, terminal):
    if recorded == current:
        return True
    if not isinstance(recorded, dict) or not isinstance(current, dict):
        return False
    keys = {'version', 'status', 'reward', 'checks', 'reason'}
    if (set(recorded) != keys or set(current) != keys
            or recorded['version'] != 'gitlab-grouped-goal-runtime-v1'
            or current['version'] != recorded['version']
            or recorded['status'] != 'failure' or recorded['reward'] != 0.0
            or recorded['reason'] is not None
            or current['status'] != 'success' or current['reward'] != 1.0
            or current['reason'] is not None):
        return False
    before, after = recorded['checks'], current['checks']
    if (not isinstance(before, dict) or not isinstance(after, dict)
            or set(before) != CHECKS or set(after) != CHECKS
            or before['native_section_identity'] is not False
            or any(before[k] is not True for k in CHECKS - {'native_section_identity'})
            or any(value is not True for value in after.values())):
        return False
    native = terminal.get('gitlab_grouped_goal', {}) if isinstance(terminal, dict) else {}
    body = native.get('body_page') if isinstance(native, dict) else None
    if not isinstance(body, str) or not body.startswith('projects:metrics_dashboard:'):
        return False
    expected = deepcopy(recorded)
    expected.update(status='success', reward=1.0)
    expected['checks']['native_section_identity'] = True
    return expected == current
