"""Original-start map-link result through the ordinary anonymous Map worker.

The explicit local-artifact training derivative preserves its already declared
public goal. Private initial-view capture supplies no strategy or answer to the
actor. The common runner scores only after its trace terminates.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from . import map_initial_view_link as rule
from . import map_view, map_reset_guard, site_worker
from .source_revision_binding import binding, fingerprint, require_source_binding
from .io_utils import atomic_write_json
from .site_navigation_rules import valid_initial_page

VERSION='map-initial-view-link-normal-runtime-v1'
PROOF='map-initial-view-link-normal-two-cold-v1'
PROFILE='ordinary-anonymous-map-worker-v1'
METHODS=['prepare','attach','observe_initial','record','capture_terminal','provide_trace','score_terminal']
EXPECTED={'initial_long':'success','initial_short':'success','no_answer':'failure',
    'wrong_view':'failure','wrong_layer':'failure','foreign_origin':'failure','404':'failure','login':'failure'}
SHA=re.compile('[0-9a-f]{64}')


def enabled(c):
    if 'map_initial_view_link' not in c:return False
    if (c.get('map_initial_view_link')!={'version':VERSION,'profile':PROFILE}
        or c.get('domain')!='map' or c.get('eligible_for_training')is not False
        or c.get('heldout_quarantine')is not False
        or any(c.get(k)for k in ('query','map_native_facts','map_native_route','map_native_layer',
            'map_export','map_zoom','map_geolocation','map_community_fixture','map_editor_runtime'))
        or c.get('completion')!={}):
        raise ValueError('One explicit initial-view result on the anonymous default Map profile required')
    binding(c)
    revision=c.get('completion_revision',{})
    if (revision.get('kind')!='explicit_local_result_contract'
        or revision.get('benchmark_equivalence_claimed')is not False
        or revision.get('original_task_id')!=c['source_task_id']
        or revision.get('original_goal')!=c['original_goal']
        or revision.get('first_start_unchanged')is not True
        or revision.get('share_panel_action_required')is not False
        or c['start_path']!=c['recorded_start_paths'][0]):
        raise ValueError('Exact declared local artifact derivative and original first start required')
    return True


def fields(c):enabled(c);return ['share_link']
def public_goal(c):enabled(c);return c['goal']
def require_original_binding(c,original,inventory):
    enabled(c);return require_source_binding(c,original,inventory,domain='map')
def provenance():
    paths={'runtime':Path(__file__),'result_rule':Path(rule.__file__),
        'native_view':Path(map_view.__file__),'full_native_guard':Path(map_reset_guard.__file__),
        'ordinary_site_worker':Path(site_worker.__file__)}
    return {k+'_sha256':hashlib.sha256(p.read_bytes()).hexdigest()for k,p in paths.items()}

def site_profile(site):
    profile={'version':PROFILE,'with_tiles':getattr(site,'with_tiles',None),
        'with_geographic_baseline':getattr(site,'with_geographic_baseline',None),
        'track_changes':getattr(site,'track_changes',None),
        'community_fixture':getattr(site,'community_fixture',None),
        'native_layer_refresh':getattr(site,'native_layer_refresh',None)}
    if (site.domain!='map' or any(profile[k]is not True for k in
        ('with_tiles','with_geographic_baseline','track_changes'))
        or profile['community_fixture']is not None or profile['native_layer_refresh']is not False
        or site.reset_guard is None):
        raise ValueError('Ordinary anonymous guarded geographic Map worker required')
    site.reset_guard.require_unchanged()
    return profile


def require_admission(c,p):
    return verify_retained_native_proof(c,p,expected_provenance=provenance())


def verify_retained_native_proof(c,p,*,expected_provenance):
    """Validate native evidence; trusted catalogs separately bind code evolution."""
    enabled(c)
    if (not isinstance(p,dict)or p.get('version')!=PROOF
        or p.get('fingerprint')!=fingerprint(c)or p.get('source_binding')!=binding(c)
        or p.get('provenance')!=expected_provenance or p.get('actor_attempts')!=0 or p.get('api_calls')!=0):
        raise ValueError('Exact same-hook actual two-cold Map link result proof required')
    cycles=p.get('cycles')
    if not isinstance(cycles,list)or len(cycles)!=2:raise ValueError('Two independent cold default-profile cycles required')
    fresh=set();baseline=None;reference=None
    for index,cycle in enumerate(cycles):
        identity=cycle.get('fresh_instance_id')
        if not isinstance(identity,str)or not SHA.fullmatch(identity)or identity in fresh:
            raise ValueError('Independent native instance identity required')
        fresh.add(identity)
        before=cycle.get('initial_fingerprint')
        if (cycle.get('cycle')!=index or not isinstance(before,str)or not SHA.fullmatch(before)
            or cycle.get('final_fingerprint')!=before or cycle.get('protected_unchanged')is not True
            or cycle.get('cold_teardown_completed')is not True):
            raise ValueError('Complete cold protection and teardown required')
        if baseline is not None and baseline!=before:raise ValueError('Independent default-profile baselines differ')
        baseline=before
        controls=cycle.get('controls')
        if not isinstance(controls,dict)or set(controls)!=set(EXPECTED):raise ValueError('All actual native result controls required')
        for name,row in controls.items():
            profile=row.get('site_profile',{})
            if (profile!={'version':PROFILE,'with_tiles':True,'with_geographic_baseline':True,
                         'track_changes':True,'community_fixture':None,'native_layer_refresh':False}
                or row.get('lifecycle')!=METHODS or row.get('provenance')!=expected_provenance
                or row.get('actual_normal_browsergym_session')is not True
                or row.get('bound_original_start_restored')is not True
                or row.get('initial_fingerprint')!=before or row.get('final_fingerprint')!=before
                or row.get('integrity')is not True or not valid_initial_page(row.get('initial_page'),site_origin=row['site_origin'])
                or row.get('initial_page',{}).get('url')!=row['site_origin']+c['start_path']):
                raise ValueError('Actual normal lifecycle/profile/start and full native guard required')
            captured=rule.reference(c,row['initial_native_view'],row['site_origin'])
            if captured!=row.get('reference'):raise ValueError('Initial actual native reference differs')
            if reference is not None and reference!=captured:raise ValueError('Normal initial view references differ')
            reference=captured
            reproduced=rule.evaluate(c,row['terminal'],row['answer'],captured,captured,site_origin=row['site_origin'])
            if reproduced!=row.get('judgment')or reproduced['status']!=EXPECTED[name]:
                raise ValueError('Actual terminal control cannot be reproduced')
            from .admin_pilot import final_answer
            if final_answer(row['trace'])!=row['answer']:raise ValueError('Answer differs from actual common rollout actions')
    return deepcopy(baseline),deepcopy(reference)


class _InitialViewHooks:
    """Private CPU constructor uses the exact normal prepare-to-score methods."""
    def __init__(self,c,baseline,directory,expected_reference=None):
        enabled(c);self.c=deepcopy(c);self.baseline=baseline;self.expected=deepcopy(expected_reference)
        self.directory=Path(directory);self.site=None;self.context=None;self.page=None
        self.events=[];self.scored=False;self.trace=None
    def prepare(self,site,username):
        if self.site is not None or username is not None:raise ValueError('One anonymous normal preparation required')
        self.profile=site_profile(site)
        if site.fingerprint()!=self.baseline:raise ValueError('Independent cold native baseline differs')
        self.site=site;self.events.append('prepare')
    def attach(self,context):
        if self.site is None or self.context is not None:raise ValueError('One normal context follows private preparation')
        self.context=context;self.events.append('attach')
    def observe_initial(self,page):
        if self.page is not None or page.context is not self.context or page.url!=self.site.url+self.c['start_path']:
            raise ValueError('Bound original start and disposable normal browser required')
        self.page=page;self.view=map_view.wait_native_view(page,self.c['start_path'])
        self.reference=rule.reference(self.c,self.view,self.site.url)
        if self.expected is not None and self.reference!=self.expected:raise ValueError('Admitted native initial view differs')
        atomic_write_json(self.directory/'initial-native-map-link-reference.json',self.reference)
        self.events.append('observe_initial')
    def record(self,page):
        if page is not self.page or page.context is not self.context or self.scored:raise ValueError('Only bound normal observations required')
        self.events.append('record')
    def capture_terminal(self,page,terminal):
        if page is not self.page or page.context is not self.context or terminal.get('url')!=page.url or self.scored:
            raise ValueError('Only bound actual normal terminal document required')
        self.terminal=deepcopy(terminal);self.events.append('capture_terminal')
    def provide_trace(self,trace):
        if not isinstance(trace,dict)or self.trace is not None or self.scored:raise ValueError('One normal completed rollout trace required')
        from .admin_pilot import final_answer
        self.trace=deepcopy(trace);self.answer=final_answer(trace);self.events.append('provide_trace')
    def score_terminal(self,site,terminal,*,runtime_error=None):
        if site is not self.site or self.scored or self.trace is None or terminal!=self.terminal:
            raise ValueError('One bound terminal-only scoring call required')
        self.scored=True;self.events.append('score_terminal')
        integrity=False
        try:
            site.reset_guard.require_unchanged();after=site.fingerprint();integrity=after==self.baseline
        except Exception:
            after=None
        result=rule.evaluate(self.c,terminal,self.answer,self.reference,self.reference,
            site_origin=site.url,runtime_error=runtime_error or ('Full native state protection unavailable' if not integrity else None))
        self.receipt={'lifecycle':list(dict.fromkeys(self.events)),'provenance':provenance(),
            'site_profile':self.profile,'site_origin':site.url,'initial_fingerprint':self.baseline,
            'final_fingerprint':after,'initial_native_view':deepcopy(self.view),
            'reference':deepcopy(self.reference),'terminal':deepcopy(terminal),
            'trace':deepcopy(self.trace),'answer':self.answer,'judgment':result,'integrity':integrity}
        atomic_write_json(self.directory/'normal-native-map-link-receipt.json',self.receipt)
        return result,integrity
    def close(self):pass

class InitialViewLinkHooks(_InitialViewHooks):
    def __init__(self,c,p,directory):
        baseline,ref=require_admission(c,p);super().__init__(c,baseline,directory,ref)

def feedback(judgment):
    return {'status':judgment['status'],'reward':judgment['reward'],
        'checks':[{'condition':k,'passed':v}for k,v in judgment['checks'].items()if type(v)is bool],
        'private_reference_values_provided':False,'action_sequence_provided':False}
