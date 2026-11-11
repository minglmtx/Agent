"""Safe failure categories: never expose arbitrary exception strings or credentials."""
class AttemptWallBudgetExceeded(TimeoutError):
    """Whole-attempt elapsed time, including browser waits, not model latency."""


def safe_failure_message(exc,stage):
    if isinstance(exc,AttemptWallBudgetExceeded):return stage+' failed: attempt_wall_budget_exhausted'
    text=str(exc).casefold()
    for fragment,code in (
        ('playwright sync api inside the asyncio loop','playwright_sync_loop_conflict'),
        ('execution context was destroyed','navigation_context_destroyed'),
        ('cannot find context with specified id','navigation_context_missing'),
        ('frame was detached','navigation_frame_detached'),
        ('target page, context or browser has been closed','browser_closed'),
        ('target crashed','browser_target_crashed'),
        ('no space left on device','storage_or_namespace_exhausted'),
        ('out of memory','memory_exhausted'),
    ):
        if fragment in text:return stage+' failed: '+code
    if type(exc).__name__=='ObservationBudgetError':return stage+' failed: observation_budget_exceeded'
    if type(exc).__name__ in ('TimeoutError','PlaywrightTimeoutError'):return stage+' failed: timeout'
    return stage+' failed; exception details unavailable (redacted)'


def failure_diagnostic(exc, stage):
    """Keep call locations and known API names without logging args/URL/locals."""
    import traceback,re
    from pathlib import Path
    message=str(exc)
    api=re.search(r'\b(Page|Frame|Locator|BrowserContext|CDPSession)\.([A-Za-z_]+):',message)
    out = {'type':type(exc).__name__,'stage':stage,'category':safe_failure_message(exc,stage),
            'api':'.'.join(api.groups()) if api else None,
            'frames':[{'file':Path(f.filename).name,'function':f.name,'line':f.lineno}
                      for f in traceback.extract_tb(exc.__traceback__)[-12:]]}
    from .site_database import DatabaseReadError
    if isinstance(exc, DatabaseReadError):
        out['database'] = {'sqlstate': exc.sqlstate, 'driver_code': exc.driver_code}
        if exc.failure_kind:out['database']['failure_kind']=exc.failure_kind
    return out


from contextlib import contextmanager
from contextvars import ContextVar

_OBS_DIAGNOSTIC_DIRECTORY=ContextVar('browser_observation_diagnostic_directory',default=None)
_PHASE_BATCH=ContextVar('runtime_phase_batch',default=None)


def instrument_observation_extractors(method):
    """Time native extraction substeps without changing outputs or retry policy.

    Wrappers are installed once in the method's globals; a context variable
    routes records to the active session and leaves other callers untouched.
    """
    from functools import wraps
    scope=getattr(getattr(method,'__func__',method),'__globals__',{})
    for name in ('_pre_extract','extract_dom_snapshot','extract_merged_axtree',
                 'extract_focused_element_bid','extract_dom_extra_properties',
                 '_post_extract','extract_screenshot'):
        original=scope.get(name)
        if not callable(original) or getattr(original,'_lab_extraction_traced',False):continue
        def wrap(fn,stage):
            @wraps(fn)
            def traced(*args,**kwargs):
                directory=_OBS_DIAGNOSTIC_DIRECTORY.get()
                if directory is None:return fn(*args,**kwargs)
                with runtime_phase(directory,stage):return fn(*args,**kwargs)
            traced._lab_extraction_traced=True
            return traced
        scope[name]=wrap(original,'browsergym_observation_'+name.lstrip('_'))

@contextmanager
def runtime_phase(directory, stage):
    import time
    from .io_utils import append_jsonl
    from pathlib import Path
    started=time.monotonic();path=Path(directory).absolute()/'runtime-phases.jsonl'
    # Diagnostic timings are not recovery/billing records. Only the outer
    # stage starts on disk; nested completion timings are flushed together.
    parent=_PHASE_BATCH.get();nested=parent is not None and parent['path']==path
    batch=parent if nested else {'path':path,'rows':[]}
    token=_PHASE_BATCH.set(batch)
    try:
        if not nested:
            append_jsonl(path,[{'stage':stage,'event':'start','time':time.time(),'monotonic':started}],durable=False)
        yield
    except BaseException as exc:
        batch['rows'].append({'event':'error','seconds':time.monotonic()-started,**failure_diagnostic(exc,stage)})
        append_jsonl(path,batch['rows'])
        batch['rows'].clear()
        raise
    else:
        batch['rows'].append({'stage':stage,'event':'completed','seconds':time.monotonic()-started})
        if not nested or len(batch['rows'])>=128:
            append_jsonl(path,batch['rows'],durable=False)
            batch['rows'].clear()
    finally:
        _PHASE_BATCH.reset(token)


def instrument_browser_startup(env, directory):
    """Trace existing BrowserGym reset phases without changing their semantics."""
    from functools import wraps
    if getattr(env, '_lab_startup_instrumented', False):
        return
    env._lab_startup_instrumented = True
    instrument_observation_extractors(env._get_obs)
    for name in ('_get_obs', '_wait_dom_loaded', '_active_page_check', '_wait_for_user_message'):
        original = getattr(env, name)
        def wrap(method, stage):
            @wraps(method)
            def traced(*args, **kwargs):
                token=_OBS_DIAGNOSTIC_DIRECTORY.set(directory) if stage=='browsergym_get_obs' else None
                try:
                    with runtime_phase(directory, stage):
                        return method(*args, **kwargs)
                finally:
                    if token is not None:_OBS_DIAGNOSTIC_DIRECTORY.reset(token)
            return traced
        setattr(env, name, wrap(original, 'browsergym' + name))
