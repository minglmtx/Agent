"""Rootless, node-local GitLab snapshot adapter for CPU admission probes."""
import getpass,json,os,re,signal,subprocess,tempfile,time,urllib.request,urllib.error
from pathlib import Path
from .admin_ports import PortLease
from .site_state_snapshot import SiteStateSnapshot
import psutil

class IsolatedGitlabSite:
 domain = "gitlab"
 def __init__(self,root,logs,*,reuse_state=False,reset_strategy="clone",prefetch_reset=False,initialization_profile=None,defer_unprepared_snapshot=False):
  self.root=Path(root);self.logs=Path(logs);self.processes=[];self.handles=[]
  self.reset_strategy=reset_strategy;self.reuse_state=reuse_state;self.events=[];self.generation=0;self.stopped=True;self.known_processes=[]
  self.prefetch_reset=prefetch_reset
  if initialization_profile not in (None,'wiki','wiki_issue','calendar_wiki_issue') or initialization_profile and not reuse_state:raise ValueError('Native initialization profile requires reusable state')
  self.initialization_profile=initialization_profile
  if type(defer_unprepared_snapshot)is not bool or defer_unprepared_snapshot and not (reuse_state and initialization_profile):raise ValueError('Deferred snapshot requires a declared reusable initialization profile')
  self.defer_unprepared_snapshot=defer_unprepared_snapshot
  self._operation_serial=0;self._reset_serial=None;self._reset_ticket=None
  if prefetch_reset and (not reuse_state or reset_strategy!='clone'):raise ValueError('Prefetch requires reusable clone state')
 def timed(self,phase,start,**extra):
  row={'phase':phase,'seconds':time.monotonic()-start,'generation':self.generation,**extra};self.events.append(row)
  path=self.logs/'timings.json';tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(self.events,indent=2));tmp.replace(path)
  return row
 def command(self,args,**kw):
  self._operation_serial+=1;self._reset_ticket=None
  return subprocess.run(self.base+args,check=True,timeout=kw.pop('timeout',180),**kw)
 def launch(self,name,args):
  self._operation_serial+=1;self._reset_ticket=None
  h=(self.logs/(str(self.generation)+'-'+name+'.log')).open('w');self.handles.append(h)
  p=subprocess.Popen(self.base+args,stdout=h,stderr=subprocess.STDOUT);self.processes.append(p);self.stopped=False
 def __enter__(self):
  if not os.environ.get('SLURM_JOB_ID') or not os.environ.get('TMPDIR'):raise RuntimeError('Slurm required')
  self.logs.mkdir(parents=True,exist_ok=True);self.temp=tempfile.TemporaryDirectory(prefix='gitlab-site-',dir=os.environ['TMPDIR']);self.state=Path(self.temp.name)
  self.ports=PortLease(count=2);self.url='http://127.0.0.1:'+str(self.ports.ports[0])
  bare=['apptainer','exec','--cleanenv','--containall','--no-home','--no-mount','bind-paths,hostfs,cwd','--pwd','/','--bind',str(self.state)+':/state']
  try:
   from .immutable_image_stage import runtime_image
   self.image=runtime_image(self.root/'containers/webarena/gitlab.sif')
   extract_started=time.monotonic()
   from .gitlab_pristine_data import populate,run_copy,EXTRACT
   try:
    if os.environ.get('LAB_GITLAB_PRISTINE_CACHE')=='1':
     extraction=populate(self.image,self.state,tmpdir=os.environ['TMPDIR'],log=self.logs/'image-copy.log')
    else:
     run_copy(bare+[str(self.image),'sh','-c',EXTRACT],log=self.logs/'image-copy.log')
     (self.state/'log').mkdir(exist_ok=True)
     extraction={'strategy':'direct_image_extract'}
   except BaseException as exc:
    self.timed('image_data_extract_failed',extract_started,error_type=type(exc).__name__);raise
   self.timed('image_data_extract',extract_started,**extraction)
   for sub in ['puma','gitlab-rails','gitaly','postgresql','redis','gitlab-workhorse','gitlab-shell']:(self.state/'log'/sub).mkdir(exist_ok=True)
   pg=self.state/'data/postgresql/data';pg.chmod(0o700)
   (pg/'postmaster.pid').unlink(missing_ok=True)
   ident=pg/'pg_ident.conf';ident.write_text('gitlab '+getpass.getuser()+' gitlab\ngitlab '+getpass.getuser()+' gitlab-psql\n'+ident.read_text())
   etc=self.state/'data/gitlab-rails/etc'
   y=etc/'gitlab.yml';s=y.read_text();s=re.sub(r'(?m)^    host: .*$', '    host: 127.0.0.1',s,count=1);s=re.sub(r'(?m)^    port: .*$', '    port: '+str(self.ports.ports[0]),s,count=1);s=re.sub(r'(?m)^    email_enabled:.*$', '    email_enabled: false',s,count=1);y.write_text(s)
   p=etc/'puma.rb';s=p.read_text().replace("bind 'tcp://127.0.0.1:8080'",'').replace('workers 16','workers 2').replace('workers: 16','workers: 2');p.write_text(s)
   g=self.state/'data/gitaly/config.toml';s=re.sub(r"(?m)^prometheus_listen_addr = .*", "prometheus_listen_addr = '127.0.0.1:"+str(self.ports.ports[1])+"'",g.read_text());g.write_text(s)
   # Retain vendor env values except host HOME; no UID-changing supervisor.
   wrapper=self.state/'service.sh';wrapper.write_text('''#!/bin/bash
set -euo pipefail
service=$1
shift
for f in /opt/gitlab/etc/"$service"/env/*; do
 [ -f "$f" ] || continue
 name=${f##*/}
 case "$name" in HOME|PYTHONPATH) continue;; esac
 export "$name=$(cat "$f")"
done
cd /var/opt/gitlab/gitlab-rails/working
exec "$@"
''')
   self.base=bare[:-2]+['--bind',str(self.state)+'/data:/var/opt/gitlab','--bind',str(self.state)+'/log:/var/log/gitlab','--bind',str(self.state)+'/optvar:/opt/gitlab/var','--bind',str(self.state)+':/state',str(self.image)]
   if self.reuse_state and not self.defer_unprepared_snapshot:
    self.baseline_temp=tempfile.TemporaryDirectory(prefix='gitlab-baseline-',dir=os.environ['TMPDIR'])
    self.snapshot=SiteStateSnapshot(self.state,Path(self.baseline_temp.name)/'state',services_stopped=lambda:self.stopped,restore_strategy=self.reset_strategy)
    baseline_started=time.monotonic();self.snapshot.save();self.timed('baseline_save',baseline_started)
    self.prepare_next_reset()
   elif self.defer_unprepared_snapshot:
    self.timed('unprepared_baseline_deferred',time.monotonic(),profile=self.initialization_profile,snapshot_saved=False,prefetch_started=False)
   self.start_services()
   if self.initialization_profile:
    from .gitlab_preinitialized_baseline import prepare
    prepare(self,self.initialization_profile)
   return self
  except BaseException:self.__exit__(None,None,None);raise
 def start_services(self):
   if not self.stopped:raise RuntimeError('Services already running')
   ready_started=time.monotonic()
   self.launch('postgres',['/opt/gitlab/embedded/bin/postgres','-D','/var/opt/gitlab/postgresql/data','-c','listen_addresses=','-c','unix_socket_directories=/var/opt/gitlab/postgresql','-c','shared_buffers=256MB'])
   from .service_readiness import wait_for_command
   def record_probe(row):
    # Metadata only: no command arguments, environment or connection secrets.
    with (self.logs/'postgres-readiness.jsonl').open('a') as stream:
     stream.write(json.dumps({'generation':self.generation,**row})+'\n')
   wait_for_command(self.base+['/opt/gitlab/embedded/bin/pg_isready','-h','/var/opt/gitlab/postgresql'],
                    service_running=lambda:self.processes[0].poll() is None,record=record_probe)
   self.launch('redis',['/opt/gitlab/embedded/bin/redis-server','/var/opt/gitlab/redis/redis.conf','--daemonize','no','--supervised','no','--port','0'])
   self.launch('gitaly',['bash','/state/service.sh','gitaly','/opt/gitlab/embedded/bin/gitaly-wrapper','/opt/gitlab/embedded/bin/gitaly','/var/opt/gitlab/gitaly/config.toml'])
   self.launch('puma',['bash','/state/service.sh','gitlab-rails','/opt/gitlab/embedded/bin/bundle','exec','puma','-C','/var/opt/gitlab/gitlab-rails/etc/puma.rb'])
   # Native GitLab shell/Gitaly hooks call the Workhorse Unix socket. The
   # browser-facing TCP listener alone cannot serve repository write checks.
   # Restore the native endpoint instead of disabling hooks or permissions.
   internal_socket=self.state/'data/gitlab-workhorse/sockets/socket'
   internal_socket.parent.mkdir(parents=True,exist_ok=True)
   if internal_socket.is_socket():internal_socket.unlink()
   elif internal_socket.exists():raise RuntimeError('Native internal socket path contains a non-socket file')
   workhorse=['bash','/state/service.sh','gitlab-workhorse','/opt/gitlab/embedded/bin/gitlab-workhorse']
   backend=['-authBackend','http://localhost:8080','-authSocket','/var/opt/gitlab/gitlab-rails/sockets/gitlab.socket','-documentRoot','/opt/gitlab/embedded/service/gitlab-rails/public','-secretPath','/opt/gitlab/embedded/service/gitlab-rails/.gitlab_workhorse_secret','-config','/var/opt/gitlab/gitlab-workhorse/config.toml']
   self.launch('workhorse-internal',workhorse+['-listenNetwork','unix','-listenAddr','/var/opt/gitlab/gitlab-workhorse/sockets/socket']+backend)
   self.launch('workhorse',workhorse+['-listenNetwork','tcp','-listenAddr','127.0.0.1:'+str(self.ports.ports[0])]+backend)
   deadline=time.monotonic()+600
   while time.monotonic()<deadline:
    if any(p.poll() is not None for p in self.processes):raise RuntimeError('GitLab service exited; inspect service logs')
    http_ready=False
    try:
     with urllib.request.urlopen(self.url+'/users/sign_in',timeout=5) as response:
      http_ready=response.status==200
    except (urllib.error.URLError,TimeoutError):pass
    if http_ready:
     # A failed background-worker startup must propagate; retrying it as if it
     # were an HTTP polling timeout could launch duplicate native workers.
     if os.environ.get('LAB_GITLAB_NATIVE_FORK_WORKER')=='1':
      from .gitlab_background import start
      start(self)
     self.timed('services_ready',ready_started);return self
    time.sleep(2)
   raise TimeoutError('GitLab HTTP readiness exceeded 600 seconds')
 def reset_state(self):
  if not self.reuse_state or not hasattr(self,'snapshot'):raise RuntimeError('Worker snapshot not enabled')
  start=time.monotonic()
  self.stop_services()
  restore=self.snapshot.restore();self.events.append({'phase':'state_restore','generation':self.generation,**restore})
  self.generation+=1
  self.prepare_next_reset()
  self.start_services()
  result=self.timed('reset_total',start,restore=restore)
  self._reset_serial=self._operation_serial;self._reset_ticket=None
  return result
 def issue_reset_handoff(self):
  # For immediate producer -> driver entry only. Never infer a clean state
  # later from generation alone, or carry a ticket across browser operations.
  if (self.stopped or self._reset_serial!=self._operation_serial or
      self._reset_ticket is not None or not self.events or self.events[-1]['phase']!='reset_total'):
   raise RuntimeError('No unused immediate full-reset handoff')
  self._reset_ticket=object()
  return self._reset_ticket
 def consume_reset_handoff(self,ticket):
  from copy import deepcopy
  if (ticket is None or ticket is not self._reset_ticket or self.stopped or
      self._reset_serial!=self._operation_serial or self.events[-1]['phase']!='reset_total'):
   raise RuntimeError('Stale or foreign reset handoff')
  self._reset_ticket=None;self._reset_serial=None
  return deepcopy(self.events[-1])
 def reset_background_processes(self):
  # Source-level browser cleanup must not kill this registered private copy.
  # Site exit still cancels it before baseline/state deletion.
  pending=getattr(getattr(self,'snapshot',None),'_prepared',None)
  return [pending[1]] if pending and pending[1].poll() is None else []
 def prepare_next_reset(self):
  if self.prefetch_reset:
   started=time.monotonic();record=self.snapshot.prepare_restore()
   self.timed('prepare_next_reset',started,**record)
 def stop_services(self):
  self._operation_serial+=1;self._reset_ticket=None
  start=time.monotonic()
  tracked=list(self.known_processes)
  for p in self.processes:
   try:
    parent=psutil.Process(p.pid);tracked.extend(parent.children(recursive=True));tracked.append(parent)
   except psutil.NoSuchProcess:pass
  # Stop application frontends before PostgreSQL. Container parents forward TERM.
  for p in reversed(self.processes):
   if p.poll() is None:
    p.terminate()
    try:p.wait(timeout=15)
    except subprocess.TimeoutExpired:p.kill();p.wait(timeout=10)
  # Do not restore data while an orphaned child could still write it.
  alive=[p for p in tracked if p.is_running() and p.status()!=psutil.STATUS_ZOMBIE]
  for p in alive:
   try:p.terminate()
   except psutil.NoSuchProcess:pass
  _,alive=psutil.wait_procs(alive,timeout=5)
  for p in alive:
   try:p.kill()
   except psutil.NoSuchProcess:pass
  _,alive=psutil.wait_procs(alive,timeout=5)
  self.known_processes=alive
  if alive:raise RuntimeError('Service descendants remain alive; refusing state restore')
  self.processes=[];self.stopped=True
  for h in self.handles:h.close()
  self.handles=[]
  self.timed('services_stop',start)
 def fingerprint(self, *, evidence_path=None):
  import hashlib
  sql="COPY (SELECT id,namespace_id,name,path FROM projects ORDER BY id) TO STDOUT WITH CSV"
  data=self.command(['/opt/gitlab/embedded/bin/psql','-h','/var/opt/gitlab/postgresql','-U','gitlab','-d','gitlabhq_production','-c',sql],capture_output=True).stdout
  # Preserve the exact bytes already read for the guard. A second query could
  # observe another state; a digest alone cannot explain a later mismatch.
  if evidence_path is not None:
   with Path(evidence_path).open('xb') as stream:stream.write(data)
  return hashlib.sha256(data).hexdigest()
 def __exit__(self,*args):
  try:self.stop_services()
  finally:
   if hasattr(self,'snapshot'):self.snapshot.close()
  if hasattr(self,'state'):
   import shutil
   for src in (self.state/'log').glob('*/*.log'):
    if src.is_file():
     with src.open('rb') as f:f.seek(max(0,src.stat().st_size-131072));(self.logs/(src.parent.name+'-'+src.name)).write_bytes(f.read())
  for h in self.handles:h.close()
  if hasattr(self,'ports'):self.ports.close()
  if hasattr(self,'temp'):self.temp.cleanup()
  if hasattr(self,'baseline_temp'):self.baseline_temp.cleanup()
