"""One browser action, then observation settling; separate failure phases.

No action retries and no task-specific strategies. Text is the actor input;
optional screenshots are review artifacts, never a success condition.
"""
from .gobrowse_runtime import BrowserGymSession
from .admin_page_wait import refresh_after_loading
from .runtime_diagnostics import runtime_phase


def _admin_browser_step(session,action,directory,*,timeout_ms=None):
    try:
        with runtime_phase(directory,'browsergym_step'):
            obs,reward,terminated,truncated,info=BrowserGymSession.step_raw(session,action)
    except Exception as exc:
        from .browser_health import record
        try:record(directory,'browsergym_step_failure',exc)
        except Exception:pass  # Evidence collection must not replace the original exception.
        raise
    if not (terminated or truncated or action.startswith(('send_msg_to_user(', 'report_infeasible('))):
        with runtime_phase(directory,'page_settle_and_observation'):
            obs=refresh_after_loading(session.env,session.observation,obs,timeout_ms=timeout_ms)
    with runtime_phase(directory,'text_capture'):
        obs=BrowserGymSession.download_observation(session,obs)
        session.capture(obs,action)
    return obs,reward,terminated,truncated,info


def admin_browser_step(session,action,directory,*,timeout_ms=None):
    import os
    from contextlib import nullcontext
    from .runtime_watchdog import deadline_scope
    from pathlib import Path
    # Includes SDK observation extraction, which may hang after renderer death.
    scope=deadline_scope('browser_action_and_observation',45,result_path=Path(directory)/'result.json') if os.environ.get('LAB_RUNTIME_WATCHDOG_STATE') else nullcontext()
    with scope:
        return _admin_browser_step(session,action,directory,timeout_ms=timeout_ms)
