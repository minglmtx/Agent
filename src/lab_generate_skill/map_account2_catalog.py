"""Source-bound signup/login intake from one exact native control archive."""
from pathlib import Path
from copy import deepcopy
from io import BytesIO
import hashlib,json,tarfile
from lab_generate_skill.provider_review_catalog import identity
from lab_generate_skill.map_account2_evidence import replay

class Account2Catalog:
    def __init__(self,config,*,project):
        self.closed=False;self.files={};self.sources={};self.descriptors={};self.config=deepcopy(config);project=Path(project)
        if config.get('family')not in ('account_signup','account_login'):raise ValueError('Explicit local account family required')
        cfg=self.read(config['contracts']);review=self.read(config['review']);plan=self.read(config['plan']);capsule=self.read(plan['runtime_capsule'])
        if review.get('passed')is not True or review.get('actor_calls')!=0 or review.get('contracts')!=config['contracts']or review.get('plan')!=config['plan']or review.get('archive')!=config['archive']or review.get('archive_index')!=config['index']:
            raise ValueError('Actual source control review binding differs')
        pins={r['path']:r['sha256']for r in plan['candidate_files']}
        if pins.get(config['contracts']['path'])!=config['contracts']['sha256']:raise ValueError('Controls used another source definition')
        for ref in plan['candidate_files']:self.read(ref,json_value=False)
        for ref in cfg['evidence_pins']:self.read(ref,json_value=False)
        required=('map_account_site','map_account_profile','map_account_observation','map_account_terminal','map_account_readout','map_account_initial','map_existing_account_site','map_existing_account_observation','map_account_mail','map_account_inbox','map_account_inbox_frontend','map_query_site','map_reset_guard','map_candidate_start','map_view','map_route','map_route_initialization_binding','site_worker','native_goal_dispatch','website_batch_profile','gobrowse_runtime')
        for module in required:
            rel='src/lab_generate_skill/'+module+'.py';self.read(dict(path=str(project/rel),sha256=capsule['members'][rel]['sha256']),json_value=False)
        rel='scripts/run_site_navigation_once.py';self.read(dict(path=str(project/rel),sha256=capsule['members'][rel]['sha256']),json_value=False)
        # The document hook is installed byte-for-byte from the control's candidate file.
        hook=config['tested_document_hook']
        if pins.get(hook['path'])!=hook['sha256']:raise ValueError('Document hook was not tested')
        self.read(dict(path=str(project/'src/lab_generate_skill/signup_document_hooks.py'),sha256=hook['sha256']),json_value=False)
        required_integration={'src/lab_generate_skill/'+name+'.py'for name in ('map_account2_catalog','map_account2_evidence','frozen_signup_document_adapter','signup_document_hooks')}
        if not required_integration<=config['integration_files'].keys():raise ValueError('Complete account integration closure required')
        replay_ref=review['replayer'];self.read(replay_ref,json_value=False)
        if config['integration_files']['src/lab_generate_skill/map_account2_evidence.py']!=replay_ref['sha256']:raise ValueError('Independent raw evidence replayer differs')
        for rel,digest in config['integration_files'].items():
            if Path(rel).is_absolute()or'..'in Path(rel).parts:raise ValueError('Relative integration member required')
            self.read(dict(path=str(project/rel),sha256=digest),json_value=False)
        raw=self.read(config['archive'],json_value=False);index=self.read(config['index'])
        if index['archive_sha256']!=config['archive']['sha256']or index.get('writer_termination_confirmed')is not True:raise ValueError('Sealed actual archive required')
        data={}
        with tarfile.open(fileobj=BytesIO(raw))as archive:
            for member in archive:
                if not member.isfile()or member.name not in index['members']or member.name in data or Path(member.name).is_absolute()or'..'in Path(member.name).parts:raise ValueError('Unexpected evidence member')
                value=archive.extractfile(member).read();expected=index['members'][member.name]
                if dict(bytes=len(value),sha256=hashlib.sha256(value).hexdigest())!=expected:raise ValueError('Evidence member changed')
                data[member.name]=value
        if set(data)!=set(index['members']):raise ValueError('Evidence archive incomplete')
        results=replay(cfg,data)
        if results!=review['recomputed_sources']:raise ValueError('Actual raw review differs')
        for c in cfg['tasks']:
            if c['candidate_completion']['family']!=config['family']:continue
            sid=c['source_task_id'];proof=results[sid];baseline=proof['baseline']
            if config['family']=='account_signup':
                admission=dict(version='native-account-normal-admission-v1',source_task_id=sid,passed=True,baseline=baseline,two_cold_environment_verified=True,ordinary_lifecycle_verified=True,account_confirmation_session_verified=True,source_specific_initial_verified=True,actor_executed=False)
            else:
                admission=dict(version='native-existing-account-normal-admission-v1',source_task_id=sid,passed=True,baseline=baseline,native_controls_verified=True,ordinary_lifecycle_verified=True,initial_anonymous_verified=True,post_reset_anonymous_verified=True,actor_executed=False)
            self.sources[sid]=dict(candidate=deepcopy(c),baseline=baseline,admission=admission)
            self.descriptors[sid]=dict(version='map-account2-source-v1',source_task_id=sid,candidate_sha256=hashlib.sha256(json.dumps(c,sort_keys=True,separators=(',',':')).encode()).hexdigest(),review_sha256=config['review']['sha256'],archive_sha256=config['archive']['sha256'])
        if len(self.sources)!=1:raise ValueError('Exactly one reviewed source per account family required')
        self.require_current()
    def read(self,ref,*,json_value=True):
        path=Path(ref['path'])
        if not path.is_absolute():raise ValueError('Absolute pinned evidence required')
        before=identity(path);raw=path.read_bytes()
        actual=hashlib.sha256(raw).hexdigest()
        if actual!=ref['sha256']:
            from .reviewed_code_evolution import accepts
            if not accepts(self,ref,path,actual,json_value=json_value):raise ValueError('Pinned account evidence changed: '+str(path))
        if identity(path)!=before:raise ValueError('Pinned account evidence changed: '+str(path))
        self.files[path]=before
        return json.loads(raw)if json_value else raw
    def require_current(self):
        if self.closed or any(identity(p)!=value for p,value in self.files.items()):raise ValueError('Account evidence changed or closed')
    def resolve(self,sid,descriptor):
        self.require_current()
        if self.descriptors.get(sid)!=descriptor:raise ValueError('Exact source descriptor required')
        from .reviewed_code_evolution import require_source
        require_source(self,sid)
        return deepcopy(self.sources[sid])
    def close(self):self.closed=True
