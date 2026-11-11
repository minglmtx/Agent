"""Stage-1 response ledger and isolated official-admin website deployment."""
from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time

from .generator_sft import fingerprint
from .io_utils import atomic_write_json
from .llm import exception_diagnostics


class ResponseCache:
    """Persist requests/responses, including inputs rejected before dispatch.

    Preflight and credit rejections are retryable on explicit resume.
    Requests with ambiguous transport outcomes never automatically repeat.
    """
    def __init__(self,directory,budget,guard=None):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        if not math.isfinite(budget) or budget<=0:raise ValueError('Budget must be finite and positive')
        self.budget=budget;self.guard=guard

    def pause(self,reason,key,details=None):
        from .stage1_budget import BudgetPause
        atomic_write_json(self.directory.parent/'run_status.json',
            {'status':'paused','reason':reason,'pending_request':key,'details':details or {},
             'resume':'Resubmit with the same run directory; completed responses/rollouts are reused.'})
        raise BudgetPause(reason,details)

    def call(self,key,messages,backend,seed,*,paid=False):
        from .stage1_budget import BudgetPause
        path=self.directory/(fingerprint(key)+'.json')
        request={'messages':messages,'model':backend.model_name,'seed':seed,
                 'settings':backend.settings.model_dump(mode='json')}
        contract=fingerprint({'key':key,**request})
        previous=None
        if path.exists():
            previous=json.loads(path.read_text())
            if previous['contract']!=contract:raise ValueError('Cached request contract changed')
            if previous['status']=='complete':
                if paid and previous['response'].get('cost') is None:self.pause('Teacher cost unknown',key)
                return previous['response']
            if previous['status'] not in ('credit_rejected','not_dispatched'):
                self.pause('Unresolved model request; inspect ledger before resuming',key)
        history=[] if previous is None else previous.get('rejected_attempts',[])
        saved={'key':key,'contract':contract,'paid':paid,'status':'started',
               'request':request,'rejected_attempts':history,'budget_check':None}
        if previous is not None and 'last_preflight_pause' in previous:
            saved['last_preflight_pause']=previous['last_preflight_pause']
        def pause_before_dispatch(reason,details=None):
            # This attempt stopped before generate(). Earlier HTTP 402
            # attempts, if any, remain recorded in rejected_attempts.
            saved.update(status='not_dispatched',
                         last_preflight_pause={'reason':reason,'details':details or {}})
            atomic_write_json(path,saved)
            self.pause(reason,key,details)
        check=None
        if paid:
            records=[json.loads(p.read_text()) for p in self.directory.glob('*.json')]
            paid_records=[r for r in records if r.get('paid')]
            if any(r['status'] not in ('complete','credit_rejected','not_dispatched') or
                   (r['status']=='complete' and r['response'].get('cost') is None) for r in paid_records):
                pause_before_dispatch('Pending/unknown teacher charge; no automatic retry')
            spent=sum(r['response']['cost'] for r in paid_records if r['status']=='complete')
            if spent>=self.budget:pause_before_dispatch('Teacher reported-cost stop line reached')
            if self.guard:
                try:check=self.guard.check(messages,backend,spent,self.budget)
                except BudgetPause as exc:pause_before_dispatch(exc.reason,exc.details)
        saved['budget_check']=check
        atomic_write_json(path,saved)
        try:result=asdict(backend.generate(messages,seed=seed))
        except Exception as exc:
            diagnostics=exception_diagnostics(exc)
            billed=getattr(exc,'generation_result',None)
            # Only actual HTTP 402 before inference is a known credit rejection.
            # HTTP-200 provider error bodies and connection loss remain ambiguous.
            http_response=getattr(exc,'response',None)
            if paid and getattr(http_response,'status_code',None)==402 and billed is None:
                history.append({'attempt':len(history)+1,'http_status':402,'diagnostics':diagnostics})
                saved.update(status='credit_rejected',rejected_attempts=history)
                atomic_write_json(path,saved)
                self.pause('openrouter_credit_rejected_402',key,{'retry_after_topup':True})
            saved.update(status='error',diagnostics=diagnostics)
            if billed is not None:saved['response']=asdict(billed)
            atomic_write_json(path,saved)
            self.pause('Model request failed; check saved diagnostics and billing before retry',key)
        cost=result.get('cost')
        if paid and (not isinstance(cost,(int,float)) or isinstance(cost,bool) or not math.isfinite(cost) or cost<0):
            saved.update(status='unknown_cost',response=result);atomic_write_json(path,saved)
            self.pause('Teacher response saved but cost is unresolved; stopping',key)
        saved.update(status='complete',response=result);atomic_write_json(path,saved)
        return result


class IsolatedAdminSite:
    """A private Admin deployment with instance-owned endpoints and port leases.

    Foreground callers expose this site's endpoints for existing browser
    integrations. Background preparation passes activate_environment=False,
    then activates the selected site only while its foreground episode runs.
    This does not by itself validate paired reset semantics or task admission.
    """
    def __init__(self,project,root,log_dir,init_task_id=None,*,activate_environment=True):
        self.project=Path(project);self.root=Path(root);self.log_dir=Path(log_dir)
        self.process=None;self.temp=None;self.log=None;self.ports=None
        self.endpoints={};self._environment_context=None;self._closed=False
        self.init_task_id=init_task_id;self.activate_environment=activate_environment

    @property
    def state(self):
        if self.temp is None:raise RuntimeError('Admin instance has not started')
        return Path(self.temp.name)

    @property
    def logs(self):return self.log_dir

    @property
    def url(self):return self.endpoints['WA_SHOPPING_ADMIN']

    @property
    def processes(self):return [self.process] if self.process is not None else []

    def activate(self):
        from .admin_instance_environment import activate
        if self._closed or not self.endpoints:raise RuntimeError('A live ready Admin instance is required')
        return activate(self.endpoints)

    def __enter__(self):
        if self.temp is not None or self._closed:raise RuntimeError('Admin instance cannot be started twice')
        if not os.environ.get('SLURM_JOB_ID') or not os.environ.get('TMPDIR'):
            raise RuntimeError('Website deployment requires a Slurm allocation and node-local TMPDIR')
        from .admin_ports import PortLease
        from .admin_instance_environment import child_port_environment, validate_endpoints
        try:
            self.ports=PortLease(count=5)
            self.temp=tempfile.TemporaryDirectory(prefix='stage1-site-',dir=os.environ['TMPDIR'])
            state=self.state;self.ready=state/'ready.json';self.stop=state/'stop'
            self.log_dir.mkdir(parents=True,exist_ok=True)
            self.log=(self.log_dir/(state.name+'.log')).open('w')
            env={**os.environ,**child_port_environment(self.ports.ports),
                 'TMPDIR':str(state),'WA_RUN_OUTPUT':str(self.log_dir/state.name),
                 'WA_IMAGE_PATH':str(self.root/'containers/webarena/shopping-admin.sif'),
                 'STAGE1_SITE_READY':str(self.ready),'STAGE1_SITE_STOP':str(self.stop),
                 'LAB_ADMIN_NODE_TMPDIR':os.environ['TMPDIR']}
            if os.environ.get('ADMIN_REUSE_PRISTINE_SEED')=='1':
                env['WA_ADMIN_SEED_CACHE']=str(Path(os.environ['TMPDIR'])/('admin-pristine-'+str(os.getpid())))
            else:env.pop('WA_ADMIN_SEED_CACHE',None)
            # A previous foreground task must not seed a new background site.
            env.pop('WA_PILOT_TASK_ID',None)
            from .admin_category_operations import definition as category_definition
            category=category_definition(self.init_task_id)
            if self.init_task_id:env['WA_PILOT_TASK_ID']=category['fixture_source_id'] if category else self.init_task_id
            launch=state/'start-admin.sh';launch.write_bytes((self.project/'cluster/start-admin.sh').read_bytes())
            self.process=subprocess.Popen(['bash',str(launch),
                'python',str(self.project/'cluster/stage1_site_bridge.py')],env=env,
                stdout=self.log,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+600
            while not self.ready.exists():
                if self.process.poll() is not None:raise RuntimeError('Website startup failed; inspect site log')
                if time.monotonic()>deadline:raise RuntimeError('Website startup exceeded 600 seconds')
                time.sleep(.5)
            self.endpoints=validate_endpoints(json.loads(self.ready.read_text()),self.ports.ports)
            if category is not None:
                from .admin_category_operations import initialize_fixture
                initialize_fixture(self,category)
            if self.activate_environment:
                self._environment_context=self.activate()
                self._environment_context.__enter__()
            return self
        except BaseException:
            self.__exit__(None,None,None);raise

    def __exit__(self,*args):
        if self._closed:return
        self._closed=True
        try:
            if self.process is not None:
                self.stop.touch()
                try:self.process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    self.process.terminate()
                    try:self.process.wait(timeout=10)
                    except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        finally:
            try:
                if self._environment_context is not None:
                    self._environment_context.__exit__(*args);self._environment_context=None
            finally:
                if self.log:self.log.close()
                if self.temp:self.temp.cleanup()
                if self.ports:self.ports.close()
