"""Separate executed-action errors from fresh-page warnings in CPU controls.

The browser protocol already exposes both fields to the actor. Private control
drivers must not turn an informational loading warning into an execution error.
This helper neither retries the action nor assumes task success or page readiness.
"""


def post_click_navigation_pending(observation):
    """Diagnostic only; never proves delivery, readiness, or task completion.

    A private control may proceed to independent state verification without
    clicking twice. The original execution error must remain in its record.
    """
    if not isinstance(observation,dict):return False
    message=observation.get('action_execution_error')
    return (isinstance(message,str) and 'TimeoutError: Locator.click:' in message
            and 'click action done' in message
            and 'waiting for scheduled navigations to finish' in message
            and 'intercepts pointer events' not in message)


def require_action_executed(observation):
    if not isinstance(observation,dict):raise ValueError('Browser observation required')
    legacy=observation.get('last_action_error','')
    if not isinstance(legacy,str):raise ValueError('Malformed browser feedback')
    if 'action_execution_error' not in observation:
        if legacy:raise ValueError('Common browser action failed: '+legacy[:500])
        return ''
    execution=observation['action_execution_error']
    warning=observation.get('page_observation_warning','')
    if not isinstance(execution,str)or not isinstance(warning,str):
        raise ValueError('Malformed split browser feedback')
    if execution:raise ValueError('Common browser action failed: '+execution[:500])
    # Never silently discard a legacy error that the split fields do not explain.
    if legacy and legacy!=warning:
        raise ValueError('Unclassified browser feedback: '+legacy[:500])
    return warning
