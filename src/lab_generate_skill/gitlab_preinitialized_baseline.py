"""Opt-in native cache initialization BEFORE an immutable rollout baseline.

Only native wiki/issue cache computations are allowed. No task, account, answer
or browser action enters this profile. Existing cold-proof baselines are not
silently reused: the prepared profile requires its own equivalence validation.
"""
import hashlib
import importlib
from pathlib import Path
import tempfile
import time

from .io_utils import atomic_write_json
from .site_state_snapshot import SiteStateSnapshot

PROFILES = {'wiki': ('wiki',), 'wiki_issue': ('wiki','issue'), 'calendar_wiki_issue': ('wiki','issue')}


def module(kind):
    if kind not in ('wiki','issue'):raise ValueError('Unsupported native initializer')
    return importlib.import_module('gitlab_native_'+kind+'_cache_init')


def prepare(site, profile):
    if profile not in PROFILES or site.generation != 0 or not site.reuse_state:
        raise ValueError('Preparation requires a new private reusable GitLab site')
    if getattr(site,'prepared_initialization',None) is not None:
        raise ValueError('Prepared baseline cannot be refreshed from task state')
    deferred=getattr(site,'defer_unprepared_snapshot',False)
    if deferred:
        if site.initialization_profile!=profile or hasattr(site,'snapshot') or hasattr(site,'baseline_temp'):
            raise ValueError('Deferred preparation must begin without an unprepared snapshot')
    elif not hasattr(site,'snapshot') or not hasattr(site,'baseline_temp'):
        raise ValueError('Original immutable baseline missing')
    start=time.monotonic();records={};before=None;after=None;original_evidence={}
    if profile == 'calendar_wiki_issue':
        from .gitlab_calendar_baseline import prepare_account
        prepare_account(site)
    for kind in PROFILES[profile]:
        initializer=module(kind)
        cold,after,effects=initializer.initialize(site,site.logs/'baseline-initialization'/kind)
        from .gitlab_prepared_cache_proof import collect_original
        original_evidence[kind]=collect_original(kind,site.logs/'baseline-initialization'/kind)
        if before is None:before=cold
        records[kind]={'initializer_sha256':hashlib.sha256(Path(initializer.__file__).read_bytes()).hexdigest(),
                       'effects':effects}
    # Keep the old immutable baseline until the independent replacement exists.
    # No working database is copied while any service may still write it.
    site.stop_services()
    if not deferred:site.snapshot.close()
    new_temp=tempfile.TemporaryDirectory(prefix='gitlab-prepared-baseline-',dir=site.state.parent)
    try:
        replacement=SiteStateSnapshot(site.state,Path(new_temp.name)/'state',
            services_stopped=lambda:site.stopped,restore_strategy=site.reset_strategy)
        replacement.save()
    except BaseException:
        new_temp.cleanup();raise
    old_temp=getattr(site,'baseline_temp',None)
    site.snapshot=replacement;site.baseline_temp=new_temp
    if old_temp is not None:old_temp.cleanup()
    site.prepared_initialization={'profile':profile,'initializers':records,
                                 'cold_before':before,'prepared_after':after,
                                 'original_evidence':original_evidence}
    site.prepare_next_reset();site.start_services()
    # Original initializer files already contain the large column vectors.
    # Reuse receipts retain them in the shared evidence store; this summary
    # does not embed another complete copy.
    atomic_write_json(site.logs/'prepared-baseline.json',
        {k:v for k,v in site.prepared_initialization.items() if k!='original_evidence'})
    site.timed('prepare_native_baseline',start,profile=profile)


def reuse(site, kind, folder):
    """Return fresh current-state evidence; never substitute a cached scan."""
    state=getattr(site,'prepared_initialization',None)
    if state is None:return None
    if kind not in state['initializers']:
        raise ValueError('Requested initializer is outside the prepared profile')
    initializer=module(kind)
    if hashlib.sha256(Path(initializer.__file__).read_bytes()).hexdigest()!=state['initializers'][kind]['initializer_sha256']:
        raise ValueError('Prepared initializer implementation changed')
    from .gitlab_native_csv_probe import protected_snapshot_session
    import gitlab_project_column_hashes as columns
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    actual=protected_snapshot_session(site,folder/'prepared-current-full16-progress.jsonl')
    if actual!=state['prepared_after']:
        raise ValueError('Current state differs from the prepared native baseline')
    current_columns=columns.snapshot(site)
    effects=initializer.verify_effects(current_columns,current_columns,actual,actual,{'rows':[]})
    atomic_write_json(folder/'prepared-cache-verification.json',{
        'profile':state['profile'],'fresh_complete16_match':True,'initializer_invoked':False,
        'effects':effects,'actor_attempts':0,'api_calls':0})
    return actual,actual,effects
