"""Bind native login controls and ordinary lifecycle evidence to one task.

No admission follows from a summary alone: archived initial/terminal readouts
are re-evaluated, reset identity is checked, and the actual tested code is pinned.
"""
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit
import json
from .account_review_catalog import AccountReviewCatalog
from .provider_review_catalog import digest
from .source_revision_binding import binding
from .map_account_profile import existing_profile_for_contracts
from .map_account_terminal import evaluate_account
from .map_existing_account_observation import VERSION,require_anonymous,unchanged_login_state
from .map_account_initial import validate_document_start

DEPENDENCIES=('site_worker','native_goal_dispatch','website_batch_profile','map_existing_account_site',
    'map_existing_account_observation','map_account_profile','map_account_observation',
    'map_account_terminal','map_account_readout','map_account_initial','map_query_site','map_reset_guard',
    'map_candidate_start','map_view','map_route','map_route_initialization_binding')
NATIVE_DEPENDENCIES=('map_existing_account_site','map_account_observation','map_account_terminal',
    'map_account_readout','map_account_initial','map_query_site','map_reset_guard')


def review_ordinary_control(candidate,initial,terminal,expected):
    state=initial['original_start'];u=urlsplit(state['url']);origin=u.scheme+'://'+u.netloc
    validate_document_start(candidate,origin,state)
    require_anonymous(initial['session'],origin)
    if terminal['initial']!=initial['account']:raise ValueError('Ordinary initial account evidence changed')
    required=['prepare','attach','observe_initial','capture_terminal','close','score_terminal']
    if terminal['events']!=required or terminal.get('capture_error')is not None:raise ValueError('Complete error-free ordinary login lifecycle required')
    protection=terminal['protection']
    integrity=unchanged_login_state(initial['guard'],protection['guard'],
        files_unchanged=protection.get('persistent_files_unchanged'),users_unchanged=protection.get('all_users_unchanged'))
    if not integrity or terminal.get('integrity')is not True:raise ValueError('Login instance integrity unavailable')
    judgment=evaluate_account(candidate['candidate_completion'],initial=initial['account'],final=terminal['final'],
        session=terminal['session'],origin=origin,integrity=integrity)
    judgment=dict(judgment,version=VERSION)
    if judgment!=terminal['judgment'] or judgment['status']!=expected:raise ValueError('Raw ordinary account evidence disagrees with reported control')
    return judgment


class ExistingAccountReviewCatalog(AccountReviewCatalog):
    def __init__(self,config,*,project):
        self.closed=False;self.files={};self.sources={};self.descriptors={};self.config=deepcopy(config)
        native_cfg=self.read(config['native_contracts']);cfg=self.read(config['contracts'])
        native_review=self.read(config['native_review']);review=self.read(config['ordinary_review'])
        plan=self.read(config['ordinary_plan']);members=self.read(config['ordinary_runtime_members'])
        native_members=self.read(config['native_runtime_members'])
        if (len(cfg['tasks'])!=1 or cfg['tasks']!=native_cfg['tasks']
                or plan['files']['contracts.json']!=config['contracts']['sha256']
                or plan['files']['runtime-members.json']!=config['ordinary_runtime_members']['sha256']
                or not all(r.get('passed')is True and r.get('actor_attempts')==0 for r in (native_review,review))):
            raise ValueError('Exact native and ordinary login evidence required')
        pins={r['path']:r['sha256']for r in cfg['evidence_pins']}
        for key in ('native_contracts','native_review','native_archive','native_index'):
            if pins.get(config[key]['path'])!=config[key]['sha256']:raise ValueError('Ordinary worker used different native evidence')
        for pin in cfg['evidence_pins']:self.read(pin,json_value=False)
        for name in DEPENDENCIES:
            rel='src/lab_generate_skill/'+name+'.py'
            self.read(dict(path=str(Path(project)/rel),sha256=members[rel]['sha256']),json_value=False)
        for name in NATIVE_DEPENDENCIES:
            rel='src/lab_generate_skill/'+name+'.py'
            if native_members[rel]['sha256']!=members[rel]['sha256']:raise ValueError('Previously verified native login implementation changed: '+name)
        rel='scripts/run_site_navigation_once.py'
        self.read(dict(path=str(Path(project)/rel),sha256=members[rel]['sha256']),json_value=False)
        raw=self.archive(config['ordinary_archive'],config['ordinary_index'])
        native_raw=self.archive(config['native_archive'],config['native_index'])
        for r,key in ((native_review,'native_archive'),(review,'ordinary_archive')):
            if r['archive_sha256']!=config[key]['sha256']:raise ValueError('Review points to different raw evidence')
        native_report=json.loads(native_raw['report.json']);report=json.loads(raw['report.json'])
        c=cfg['tasks'][0];sid=c['source_task_id'];binding(c);existing_profile_for_contracts([c])
        if c.get('split')!='train'or c.get('heldout_quarantine'):raise ValueError('Training-only login derivative required')
        if (any(r.get('source_task_id')!=sid or r.get('passed')is not True or r.get('site_closed')is not True for r in (report,native_report))
                or report.get('clean_site_reused')is not True or report['baseline']!=native_report['baseline']):
            raise ValueError('Matching clean native baseline and closed workers required')
        required={'noop':'failure','unsubmitted':'failure','wrong-account':'failure','positive':'success','after-reset-noop':'failure'}
        if len(native_report['controls'])!=5 or {r['name']:r['status']for r in native_report['controls']}!=required:
            raise ValueError('Full native identity controls required')
        for name,expected in required.items():
            row=json.loads(native_raw[name+'/result.json']);u=urlsplit(row['terminal']['url']);origin=u.scheme+'://'+u.netloc
            if row.get('integrity')is not True or row['guard']['changed']:raise ValueError('Native control state was modified')
            computed=evaluate_account(c['candidate_completion'],initial=row['initial'],final=row['final'],session=row['session'],origin=origin)
            if computed!=row['judgment']or computed['status']!=expected:raise ValueError('Raw native control mismatch')
        if len(report['controls'])!=2 or [r['name']for r in report['controls']]!=['positive','after-reset-noop']:
            raise ValueError('Ordinary positive and reset controls required')
        for name,expected in [('positive','success'),('after-reset-noop','failure')]:
            review_ordinary_control(c,json.loads(raw[name+'/account-initial.json']),json.loads(raw[name+'/account-terminal.json']),expected)
        baseline=report['baseline']
        descriptor=dict(version='reviewed-existing-account-source-v1',source_task_id=sid,
            candidate_sha256=digest(json.dumps(c,sort_keys=True,separators=(',',':')).encode()),
            native_review_sha256=config['native_review']['sha256'],ordinary_review_sha256=config['ordinary_review']['sha256'])
        admission=dict(version='native-existing-account-normal-admission-v1',source_task_id=sid,baseline=baseline,
            passed=True,native_controls_verified=True,ordinary_lifecycle_verified=True,initial_anonymous_verified=True,
            post_reset_anonymous_verified=True,actor_executed=False)
        self.sources[sid]=dict(candidate=deepcopy(c),baseline=baseline,admission=admission)
        self.descriptors[sid]=descriptor;self.require_current()
