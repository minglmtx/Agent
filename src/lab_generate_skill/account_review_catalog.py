"""Reuse source-specific signup starts and one shared worker acceptance.

Account values are public task parameters. Shared controls establish the account
factory, confirmation/session evaluator and cold replacement, not actor outcomes
for other sources. Raw archives stay single-copy and are read without extraction.
"""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import tarfile
from urllib.parse import urlsplit
from .route_review_catalog import RouteReviewCatalog
from .provider_review_catalog import digest
from .source_revision_binding import binding
from .map_account_profile import profile_for_contracts
from .map_candidate_start import validate_initial

DEPENDENCIES=('site_worker','native_goal_dispatch','website_batch_profile',
    'map_account_site','map_account_profile','map_account_observation',
    'map_account_terminal','map_account_readout','map_account_inbox',
    'map_account_inbox_frontend','map_account_mail','map_query_site','map_reset_guard',
    'map_candidate_start','map_view','map_route','map_route_initialization_binding')


def require_reset_review(review):
    if (review.get('passed')is not True or review.get('actor_attempts')!=0
            or review.get('old_instance_closed_before_next')is not True
            or review.get('site_closed')is not True
            or review.get('controls')!=[{'control':'positive','status':'success'},
                {'control':'unconfirmed','status':'failure'},
                {'control':'after-reset-noop','status':'failure'}]):
        raise ValueError('Confirmed signup and clean ordinary-worker replacement required')


def require_source_initial(candidate,record):
    if (record.get('source_task_id')!=candidate['source_task_id']
            or record.get('passed')is not True
            or record.get('lifecycle')!=['attach','observe_initial','capture_terminal','close']
            or record.get('terminal',{}).get('http_status')!=200):
        raise ValueError('Source-specific original account start required')
    state=record['original_start'];u=urlsplit(state['url']);origin=u.scheme+'://'+u.netloc
    validate_initial(candidate,origin,state['url'],state['view'],state['route'])


class AccountReviewCatalog(RouteReviewCatalog):
    def archive(self,record,index_record):
        raw=self.read(record,json_value=False);index=self.read(index_record)
        if index['sha256']!=record['sha256']:raise ValueError('Account archive/index mismatch')
        values={}
        with tarfile.open(fileobj=BytesIO(raw))as archive:
            for m in archive:
                if (not m.isfile()or m.name not in index['files']or m.name in values
                        or Path(m.name).is_absolute()or '..'in Path(m.name).parts):
                    raise ValueError('Unexpected account evidence member')
                body=archive.extractfile(m).read()
                if index['files'][m.name]!=dict(bytes=len(body),sha256=digest(body)):
                    raise ValueError('Account evidence member changed')
                values[m.name]=body
        if set(values)!=set(index['files']):raise ValueError('Account evidence incomplete')
        return values

    def __init__(self,config,*,project):
        self.closed=False;self.files={};self.sources={};self.descriptors={};self.config=deepcopy(config)
        source_config=self.read(config['source_contracts']);starts=self.read(config['start_review'])
        current=self.read(config['worker_contracts']);review=self.read(config['worker_review'])
        plan=self.read(config['worker_plan']);members=self.read(config['worker_runtime_members'])
        require_reset_review(review)
        if (starts.get('passed')is not True or starts.get('actor_attempts')!=0
                or starts.get('signup_confirmation_native_verified')is not True
                or any(starts.get('independent_factory_reset_checks',{}).get(k)is not True
                    for k in ('old_account_absent','mail_empty','old_token_absent','old_session_rejected'))
                or plan['files']['contracts.json']!=config['worker_contracts']['sha256']
                or plan['files']['runtime-members.json']!=config['worker_runtime_members']['sha256']
                or review['archive']!=config['worker_archive']['path']
                or review['archive_sha256']!=config['worker_archive']['sha256']
                or starts['archive_sha256']!=config['start_archive']['sha256']):
            raise ValueError('Original starts or worker evidence differs')
        pins={r['path']:r['sha256']for r in current['evidence_pins']}
        for key in ('source_contracts','start_review'):
            if pins.get(config[key]['path'])!=config[key]['sha256']:
                raise ValueError('Worker did not use these original sources and starts')
        for pin in current['evidence_pins']:self.read(pin,json_value=False)
        for name in DEPENDENCIES:
            rel='src/lab_generate_skill/'+name+'.py'
            self.read(dict(path=str(Path(project)/rel),sha256=members[rel]['sha256']),json_value=False)
        rel='scripts/run_site_navigation_once.py'
        self.read(dict(path=str(Path(project)/rel),sha256=members[rel]['sha256']),json_value=False)
        original=self.archive(config['start_archive'],config['start_index'])
        worker=self.archive(config['worker_archive'],config['worker_index'])
        report=json.loads(worker['report.json'])
        if (report.get('passed')is not True or report.get('site_closed')is not True
                or report.get('old_instance_closed_before_next')is not True
                or report['source_task_id']!=review['source_task_id']):
            raise ValueError('Actual worker lifecycle was not completed')
        representative=current['tasks'][0]
        if len(current['tasks'])!=1 or representative['source_task_id']!=review['source_task_id']:
            raise ValueError('Exact representative contract required')
        self.baseline=current['baseline']
        prior_report=json.loads(original['report.json'])
        if prior_report['final_clean_factory']['native_baseline']!=self.baseline:
            raise ValueError('Initial baseline changed')
        # Every candidate owns its exact initial observation. One validated
        # parameterized signup implementation serves all public account values.
        layout={r['source_task_id']:r for r in starts['initial_layout_sources']}
        candidates=[c for c in source_config['tasks']if c['source_task_id']in layout]
        if (not candidates or len(candidates)!=len(layout)
                or {c['source_task_id']for c in candidates}!=set(layout)):
            raise ValueError('Signup source coverage changed')
        if representative not in candidates:raise ValueError('Worker representative differs from source contract')
        for c in candidates:
            sid=c['source_task_id'];binding(c);profile_for_contracts([c])
            if (c.get('split')!='train' or c.get('heldout_quarantine')
                    or layout[sid].get('original_start_validated')is not True
                    or layout[sid].get('header_does_not_hide_form')is not True):
                raise ValueError('Validated original training account start required')
            initial=json.loads(original['cold-0/initial-layout-controls/'+sid+'/result.json'])
            require_source_initial(c,initial)
            descriptor=dict(version='reviewed-native-account-source-v1',source_task_id=sid,
                candidate_sha256=digest(json.dumps(c,sort_keys=True,separators=(',',':')).encode()),
                worker_review_sha256=config['worker_review']['sha256'],
                start_review_sha256=config['start_review']['sha256'])
            admission=dict(version='native-account-normal-admission-v1',passed=True,
                source_task_id=sid,baseline=self.baseline,two_cold_environment_verified=True,
                ordinary_lifecycle_verified=True,account_confirmation_session_verified=True,
                source_specific_initial_verified=True,shared_controls_source=representative['source_task_id'],
                actor_executed=False)
            self.sources[sid]=dict(candidate=deepcopy(c),baseline=self.baseline,admission=admission)
            self.descriptors[sid]=descriptor
        self.require_current()
