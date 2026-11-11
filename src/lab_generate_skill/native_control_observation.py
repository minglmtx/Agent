"""Separate execution errors from bounded observation waits in CPU controls.

This does not declare task success or retry an action. The native control must
still establish its expected terminal condition and run the full evaluator.
"""
LOADING_WARNING = ('Page observation: the loading wait expired. This is a fresh '
                   'observation; the page may still be updating. Assess the current content.')


def require_executed_control_action(observation):
    feedback = observation.get('last_action_error', '')
    if not feedback:
        return
    wait = observation.get('page_wait', {})
    if (observation.get('action_execution_error') == ''
            and observation.get('page_observation_warning') == LOADING_WARNING
            and feedback == LOADING_WARNING
            and wait.get('status') == 'wait_budget_exhausted'
            and wait.get('observation_refreshed') is True
            and not observation.get('network_feedback')):
        return
    raise ValueError('Native CPU control execution or observation error: ' + str(feedback)[:1000])
