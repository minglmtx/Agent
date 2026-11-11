"""Unified native clone/calendar/Atom hooks and complete retained-control gates. Public browser policies come from the current runner; no archived runner or CPU bootstrap is imported."""
from copy import deepcopy

import hashlib,json,re,tempfile

from pathlib import Path

from urllib.parse import urlsplit

from . import native_artifact_state as shared

from . import native_artifact_client as client

from . import native_artifact_workspace as workspace

from lab_generate_skill.io_utils import atomic_write_json as write

from lab_generate_skill.source_revision_binding import binding

from lab_generate_skill.gitlab_native_read_runtime import full_snapshot

from lab_generate_skill.gitlab_persisted_goal_runtime import refs_snapshot,validate_refs

from lab_generate_skill.gitlab_native_csv_probe import auth_backup,restore_auth_metadata,protected_snapshot_session

from lab_generate_skill.runtime_watchdog import deadline_scope

VERSION='gitlab-artifact-source-native-full-controls-v2'

FAMILIES={'gitlab_local_artifact.clone','gitlab_local_artifact.calendar','gitlab_local_artifact.atom'}

from lab_generate_skill import gitlab_subscription_runtime as subscriptions

from lab_generate_skill import gitlab_subscription_observation as subscription_observation

def scoped_subscription(c):
 return 'required_successful_fetches' in c.get('public_parameters',{})

def legacy_calendar(c):
 return c['family'].endswith('.calendar') and not scoped_subscription(c)

class PendingCapability(ValueError):pass

def read(path):return json.loads(Path(path).read_text())

def artifact(folder,name):return shared._artifact_file(folder,name)

def enabled(c):
 binding(c)
 if c.get('driver_key')!='gitlab-artifact-source' or c.get('family')not in FAMILIES:raise ValueError('Explicit reviewed source artifact driver required')
 p=c['public_parameters']
 if c['family'].endswith('.clone'):
  if not isinstance(p.get('project'),str)or not re.fullmatch('[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+',p['project']):raise ValueError('Explicit original public native clone project required')
  # binding(c) validates the original recorded start or an explicit revision.
  # A repository artifact target does not imply a repository-home start.
 elif scoped_subscription(c):subscriptions.feed_spec(c)
 elif p!={'scope':'current_account_global_dashboard_issues','collection':'issues','kind':'calendar','client':'attempt_local_persisted_subscription'}:raise ValueError('Calendar needs explicit declared global scope and actual local client')
 if c.get('original_benchmark_equivalence')is not False:raise ValueError('Local client adaptation must declare original non-equivalence')
 return True

def public_goal(c):
 enabled(c)
 return c['goal']+'\nPublic task parameters: '+json.dumps(c['public_parameters'],sort_keys=True)

def expectations(c):
 enabled(c)
 names={'initial_no_op':'failure','positive':'success','link_only':'failure','wrong_object':'failure','404':'failure','login':'failure'}
 if c['family'].endswith('.clone'):names.update(dirty_checkout='failure')
 else:
  names.update(inactive='failure')
  if not scoped_subscription(c) or subscriptions.feed_spec(c)['required_successful_fetches']>1:names.update(unrefreshed='failure')
 return names

def normalize_origin(value,origin):
 # Only the exact ephemeral leased origin differs between two native workers.
 # Foreign URLs, query parameters, tokens, fragments and object paths survive.
 if isinstance(value,str):return value.replace(origin.rstrip('/')+'/', 'http://leased-native.invalid/')
 if isinstance(value,list):return[normalize_origin(x,origin)for x in value]
 if isinstance(value,dict):return{k:normalize_origin(v,origin)for k,v in value.items()}
 return value

def calendar_semantics(body,origin):
 from lab_generate_skill.gitlab_local_artifacts_v2 import parse_feed
 parse_feed(body,'calendar')
 text=body.decode('utf-8-sig');lines=[]
 for line in text.replace('\r\n','\n').replace('\r','\n').split('\n'):
  if line.startswith((' ','\t')):
   if not lines:raise ValueError('Malformed native calendar continuation')
   lines[-1]+=line[1:]
  elif line:lines.append(line)
 # Preserve every property and component, not just entry IDs. Arbitrary text
 # or invented keywords never replaces the full current native calendar.
 return normalize_origin(lines,origin)

class Hooks:
 def __init__(self,c,private,directory,*,proof=None,proof_session=None):
  enabled(c);self.contract=deepcopy(c);self.private=deepcopy(private);self.directory=Path(directory)
  if proof is None:raise ValueError('Current artifact hooks require complete native admission proof')
  elif proof_session is not None:
   from .native_proof_session import NativeProofSession
   if not isinstance(proof_session,NativeProofSession):raise ValueError('Trusted native proof session required')
   proof_session.reuse_verified(c,proof)
  else:require_two_cold(c,proof['cycles'],proof['directories'])
  self.proof=proof;self.site=self.context=self.page=self.actions=None
  self.events=[];self.captures=[];self.issued=[];self.pending=None
  self.prepared=self.scored=self.closed=False;self.sealed=None;self.feed=None;self.native_reader=None

  self.terminal = None; self.current_page = None; self.closed = False
 def prepare(self,site,username):
  if self.prepared or site.domain!='gitlab':raise ValueError('One real native preparation required')
  self.site=site;self.username=username
  self.fixture=None;prepared_calendar=False
  if self.contract.get('gitlab_cache_initialization')!=getattr(site,'initialization_profile',None):raise ValueError('Actual native cache profile differs from admitted contract')
  if legacy_calendar(self.contract):
   from lab_generate_skill import gitlab_calendar_baseline as fixture
   prepared_calendar=getattr(site,'initialization_profile',None)==fixture.PROFILE
   if prepared_calendar:
    self.fixture,self.cold,self.before,self.effects,self.refs_before=fixture.prepare_reused(site,username,self.directory/'calendar-account-fixture',self.directory/'cache-initialization')
   else:self.fixture=fixture.initialize(site,username,self.directory/'calendar-account-fixture')
  if not prepared_calendar:
   self.cold,self.before,self.effects=shared.initialize_baseline(site,self.directory/'cache-initialization')
   self.refs_before=refs_snapshot(site)
  full_snapshot(self.before);self.auth=auth_backup(site,username)
  if self.private.get('username',username)!=username:raise ValueError('Current account differs from source reference')
  if self.proof is not None:
   r=self.proof['cycles'][0]['controls']['initial_no_op']
   if(self.cold,self.before,self.refs_before)!=(r['native_before_initialization'],r['protected_before'],r['refs_before']):raise ValueError('Fresh complete native baseline differs from actual two-cold proof')
  self.prepared=True;self.events.append('prepare')
 def attach(self,context):
  if not self.prepared or self.context is not None:raise ValueError('One actual browser context required')
  self.context=context;self.events.append('attach')
 def observe_initial(self,page):
  page_lifetime.live_page(self, page, initial=True)
  if self.page is not None or page.context is not self.context or page.url!=self.site.url+self.contract['start_path']:raise ValueError('Original declared start required')
  self.page=page;self.events.append('observe_initial');self.record(page)
 def record(self,page):
  page_lifetime.live_page(self, page)
  from probe_gitlab_artifact_capabilities_v2 import PUBLIC
  capture=page.evaluate(PUBLIC);self.captures.append(capture);self.pending=capture;self.events.append('record')
 def acknowledge_issued(self,ax):
  if not isinstance(ax,str)or not ax.strip():raise ValueError('Actual issued AX required')
  if self.pending is not None:self.issued.append({'capture':deepcopy(self.pending),'actual_issued_ax':ax,'actual_issued_ax_sha256':hashlib.sha256(ax.encode()).hexdigest()});self.pending=None
 def bind_client(self,actions):
  if self.actions is not None or actions.origin!=self.site.url:raise ValueError('One fresh actual client required')
  self.actions=actions
  if scoped_subscription(self.contract):
   from lab_generate_skill.gitlab_subscription_session import ReferenceSession
   self.native_reader=ReferenceSession(self.site,self.directory/'native-reader')
   self.feed=subscription_observation.capture(self.site,self.username,self.contract,self.context,self.directory,client=client,reader=self.native_reader)
  elif legacy_calendar(self.contract):
   # BrowserGym installs active-page bindings on its actor context. A new
   # evaluator tab in that context would replace env.page and closing it would
   # leave a stale terminal page. Keep private browsing in a separate context.
   from lab_generate_skill.browser_reference_context import private_reference_context
   with private_reference_context(self.context) as reference_context:
    page=reference_context.new_page()
    from lab_generate_skill.browser_page_wait import settle_gitlab_capture
    from probe_gitlab_artifact_capabilities_v2 import PUBLIC,native_feed_choices
    response=page.goto(self.site.url+self.private['collection_path'],wait_until='domcontentloaded',timeout=60000)
    settle_gitlab_capture(page)
    if response is None or response.status!=200 or page.url!=self.site.url+self.private['collection_path']:raise PendingCapability('Native global issues collection unavailable')
    state=page.evaluate(PUBLIC);choices=native_feed_choices(state,self.site.url,{'collection':'issues','kind':'calendar'})
    if len(choices)!=1 or urlsplit(choices[0]).path!=self.private['feed_path']:raise PendingCapability('Original native global issue calendar is absent or ambiguous')
    actual=reference_context.request.get(choices[0],timeout=45000,max_redirects=0)
    body,parsed=client.fetched_feed(actual,'calendar')
    if actual.url!=choices[0]:raise PendingCapability('Independent native calendar response changed resource')
    path=self.directory/'private-native-calendar-response.bin';path.write_bytes(body);path.chmod(0o600)
    self.feed={'url':choices[0],'status':actual.status,'kind':'calendar','response_pin':workspace.pin(path),
     'parsed':parsed,'semantics':calendar_semantics(body,self.site.url),'native_public_capture':state}
    write(self.directory/'private-native-calendar-reference.json',self.feed)
 def capture_terminal(self,page,terminal):
  page_lifetime.terminal_page(self, page, terminal)
  self.terminal=terminal;self.events.append('capture_terminal')
 def close(self):
  if self.closed:return
  self.closed=True
  if self.actions is not None:
   self.sealed=workspace.seal(self.actions.root,self.directory/'actual-client-workspace.tar.gz')
   write(self.directory/'actual-client-workspace.json',self.sealed)
  self.events.append('close')
 def score_terminal(self,site,terminal,*,runtime_error=None):
  score_complete = page_lifetime.score_bound(self, site, terminal, runtime_error)
  if self.sealed is None and not runtime_error:raise ValueError('Complete actual sealed client state required without a runtime error')
  score_complete = score_complete and self.sealed is not None
  self.scored=True;self.events.append('score_terminal');restore_auth_metadata(site,self.auth)
  reference_stable=True
  try:
   if scoped_subscription(self.contract) and self.feed is not None:
    self.feed=subscription_observation.finish(site,self.contract,self.feed,self.directory,reader=self.native_reader)
    reference_stable=self.feed['reference_unchanged']
  finally:
   if self.native_reader is not None:self.native_reader.close()
  after=protected_snapshot_session(site,self.directory/'full16-after-progress.jsonl');full_snapshot(after);refs_after=refs_snapshot(site)
  integrity=reference_stable and self.before==after and self.refs_before==refs_after and self.auth==auth_backup(site,self.username)
  if not score_complete or not integrity:result={'status':'unknown','reward':None,'checks':{'complete_native_protection':integrity,'runtime_complete':not bool(runtime_error)}}
  else:result=evaluate(self.contract,self.private,self.feed,terminal,self.site.url,self.directory,self.sealed)
  self.receipt={'version':VERSION,'contract':self.contract,'original_binding':binding(self.contract),'private_reference':self.private,'site_origin':site.url,
   'native_before_initialization':self.cold,'native_initialization_effects':self.effects,'protected_before':self.before,'protected_after':after,'refs_before':self.refs_before,'refs_after':refs_after,
   'native_auth_baseline':self.auth,'account_fixture':self.fixture,'terminal':deepcopy(terminal),'captures':self.captures,'issued_observations':self.issued,'events':self.events,
   'private_calendar':self.feed,'sealed_client':self.sealed,'judgment':result,'integrity':integrity,'actor_attempts':0,'api_calls':0,'training_admitted':False,'normal_gate_passed':False}
  write(self.directory/'native-private-receipt.json',self.receipt);return result,integrity

def evaluate(c,private,feed,terminal,origin,directory,sealed):
 from lab_generate_skill.site_navigation_rules import valid_initial_page
 checks={'valid_final_document':valid_initial_page(terminal,site_origin=origin),'actual_artifact_completion':False}
 with tempfile.TemporaryDirectory(prefix='full-native-client-recheck-')as tmp:
  root=workspace.restore(artifact(directory,'actual-client-workspace.tar.gz'),sealed,Path(tmp)/'actual')
  if c['family'].endswith('.clone'):
   expected=origin+'/'+private['project']+'.git'
   for path in sorted((root/'repositories').iterdir()):
    if path.is_dir()and not path.is_symlink()and client.clone_completion(path,expected_url=expected,reference=private)['passed']:checks['actual_artifact_completion']=True
  elif scoped_subscription(c):
   reference=subscription_observation.verify(c,feed,directory,origin=origin,artifact=artifact,client=client)
   local=client.SubscriptionClient.__new__(client.SubscriptionClient);local.root=root/'subscriptions'
   judged=subscriptions.evaluate_client(c,local,reference,origin=origin,username=private['username'],expected_url=feed['url'],regular=client.regular)
   checks.update(judged['checks']);checks['actual_artifact_completion']=judged['status']=='success'
  else:
   if not isinstance(feed,dict)or feed.get('status')!=200 or feed.get('kind')!='calendar' or urlsplit(feed['url']).path!=private['feed_path']:raise ValueError('Actual complete independent native calendar reference required')
   raw=artifact(directory,'private-native-calendar-response.bin').read_bytes()
   if workspace.pin(artifact(directory,'private-native-calendar-response.bin'))!=feed['response_pin']or client.parse_feed(raw,'calendar')!=feed['parsed']or calendar_semantics(raw,origin)!=feed['semantics']:raise ValueError('Independent actual calendar bytes differ')
   local=client.SubscriptionClient.__new__(client.SubscriptionClient);local.root=root/'subscriptions'
   for folder in sorted(local.root.iterdir()):
    if not folder.is_dir()or folder.is_symlink():continue
    if local.completion(folder.name,expected_url=feed['url'],expected_kind='calendar',expected_parsed=feed['parsed']):
     record=read(client.regular(folder,'state.json'))
     if all(calendar_semantics(client.regular(folder,event['body_file']).read_bytes(),origin)==feed['semantics']for event in record['refreshes']):checks['actual_artifact_completion']=True
 return {'status':'success'if all(checks.values())else'failure','reward':1. if all(checks.values())else 0.,'checks':checks}

def require_reset(row):
 if row.get('generation_after')!=row.get('generation_before',-2)+1 or row.get('event',{}).get('phase')!='reset_total'or row['event'].get('restore',{}).get('restore_complete')is not True:raise ValueError('Actual full native reset receipt required')

def require_control(c,row,expected,folder):
 enabled(c)
 if row.get('version')!=VERSION or row.get('original_binding')!=binding(c)or row.get('contract')!=c or read(artifact(folder,'native-private-receipt.json'))!=row:raise ValueError('Original complete source control/raw binding required')
 if legacy_calendar(c):
  from lab_generate_skill import gitlab_calendar_baseline as fixture
  init=fixture.verify(Path(folder)/'calendar-account-fixture',row['account_fixture'])
  if init['full_after']!=row['native_before_initialization']:raise ValueError('Exact fixture to cache initializer baseline chain differs')
 elif row.get('account_fixture')is not None:raise ValueError('Unrelated task cannot introduce account fixture')
 shared.verify_initialization(folder,row)
 for name in('native_before_initialization','protected_before','protected_after'):full_snapshot(row[name])
 validate_refs(row['refs_before']);validate_refs(row['refs_after'])
 if row['protected_before']!=row['protected_after']or row['refs_before']!=row['refs_after']or row.get('integrity')is not True:raise ValueError('Full16/all-native-ref unchanged protection required')
 if row.get('api_calls')!=0 or row.get('actor_attempts')!=0 or row.get('normal_gate_passed')is not False or row.get('training_admitted')is not False:raise ValueError('Unadmitted actual CPU controls required')
 events=row['events']
 if events[:3]!=['prepare','attach','observe_initial']or events[-3:]!=['capture_terminal','close','score_terminal']or not row['issued_observations']:raise ValueError('Actual complete ordinary lifecycle/issued AX required')
 for observation in row['issued_observations']:
  if observation.get('actual_issued_ax_sha256')!=hashlib.sha256(observation['actual_issued_ax'].encode()).hexdigest()or observation.get('capture')not in row['captures']:raise ValueError('Actual original issued AX/content differs')
 first=read(artifact(folder,'step-000.json'))['observation']
 if first.get('goal')!=public_goal(c)or not first.get('axtree_txt'):raise ValueError('Actual first ordinary input required')
 if read(artifact(folder,'terminal-page.json'))!=row['terminal']or read(artifact(Path(folder).parent,'private-reference.json'))!=row['private_reference']:raise ValueError('Original terminal/reference differs')
 if read(artifact(folder,'actual-client-workspace.json'))!=row['sealed_client']:raise ValueError('Actual complete client seal differs')
 if legacy_calendar(c)and read(artifact(folder,'private-native-calendar-reference.json'))!=row['private_calendar']:raise ValueError('Actual complete native calendar reference differs')
 result=evaluate(c,row['private_reference'],row['private_calendar'],row['terminal'],row['site_origin'],folder,row['sealed_client'])
 if result!=row['judgment']or result['status']!=expected:raise ValueError('Complete original artifact predicate/expected control differs')
 return(row['native_before_initialization'],row['protected_before'],row['refs_before'])

def require_two_cold(c,cycles,directories):
 enabled(c)
 if not isinstance(cycles,list)or len(cycles)!=2 or len(directories)!=2:raise ValueError('Two complete actual cold source directories required')
 ids=[x.get('fresh_instance_id')for x in cycles]
 if any(not re.fullmatch('[0-9a-f]{64}',v or'')for v in ids)or ids[0]==ids[1]:raise ValueError('Distinct actual native cold identities required')
 baselines=[];references=[];feeds=[]
 from .native_artifact_state import close_receipt
 for cycle,folder in zip(cycles,directories):
  if read(artifact(folder,'cycle.json'))!=cycle or cycle.get('version')!=VERSION or cycle.get('source_task_id')!=c['source_task_id']or cycle.get('contract')!=c:raise ValueError('Original complete source cycle/materialization required')
  if read(artifact(folder,'materialized-contract.json'))!=c:raise ValueError('Exact source materialization differs')
  expected=expectations(c)
  if set(cycle['controls'])!=set(expected)or set(cycle['reset_controls'])!=set(expected):raise ValueError('All ordinary control/reset branches required')
  local=[]
  for name,status in expected.items():
   local.append(require_control(c,cycle['controls'][name],status,Path(folder)/name));require_reset(cycle['reset_controls'][name])
  if any(v!=local[0]for v in local):raise ValueError('Full native reset baselines disagree')
  final=read(artifact(folder,'final-reset.json'));require_reset(final)
  if final!=cycle['final_reset']or(final['cold'],final['before'],final['refs'])!=local[0]:raise ValueError('Actual complete final reset differs')
  if legacy_calendar(c):
   from lab_generate_skill import gitlab_calendar_baseline as fixture
   actual=fixture.verify(Path(folder)/'final-reset'/'calendar-account-fixture',final['account_fixture'])
   if actual['full_after']!=final['cold']:raise ValueError('Actual final fixture/reset chain differs')
  shared.verify_initialization(Path(folder)/'final-reset',{'native_initialization_effects':final['effects'],'native_before_initialization':final['cold'],'protected_before':final['before']})
  reference=read(artifact(folder,'private-reference.json'))
  if reference!=final['private_baseline']:raise ValueError('Actual private source baseline not restored')
  cleanup=close_receipt(Path(folder).parent)
  if cleanup['fresh_instance_id']!=cycle['fresh_instance_id']:raise ValueError('Actual worker cleanup/source cold identity differs')
  baselines.append(local[0]);references.append(reference)
  if scoped_subscription(c):
   records=[cycle['controls'][name]['private_calendar']['before'] for name in expected]
   if any(not subscriptions.stable_reference(records[0],v) for v in records):raise ValueError('Native feed selection changes across reset controls')
   feeds.append({k:records[0].get(k)for k in ('kind','username','account_id','project_id','selected_rows','rows','sort','native_date','native_options')})
  if legacy_calendar(c):
   records=[normalize_origin(cycle['controls'][name]['private_calendar'],cycle['controls'][name]['site_origin'])for name in expected]
   # Raw pins can legitimately differ only if exact origin text differs; full
   # native parsed structure/semantics/resource query must remain equivalent.
   for record in records:record.pop('response_pin')
   if any(v!=records[0]for v in records):raise ValueError('Actual complete calendar scope/content changes across reset controls')
   feeds.append(records[0])
 if references[0]!=references[1]or baselines[0]!=baselines[1]or feeds and feeds[0]!=feeds[1]:raise ValueError('Both actual cold source/native/client baselines must match')
 return{'version':VERSION,'passed':True,'source_task_id':c['source_task_id'],'contract':deepcopy(c),'fresh_instance_ids':ids,'fresh_cycles':2,'ordinary_controls_per_cold':len(expectations(c)),'actor_attempts':0,'api_calls':0,'training_admission_written':False}

from . import native_artifact_page_lifetime as page_lifetime
