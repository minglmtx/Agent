"""Current native callback port; original runner and CPU constructors excluded."""
from copy import deepcopy

import hashlib,json,re

from pathlib import Path

from urllib.parse import quote,urlsplit

from . import gitlab_next_components as component

from . import gitlab_next_native as native

from . import gitlab_next_state as shared

from . import gitlab_next_public as public

from lab_generate_skill.io_utils import atomic_write_json as write

from lab_generate_skill.source_revision_binding import binding

from lab_generate_skill.gitlab_native_read_runtime import full_snapshot

from lab_generate_skill.gitlab_persisted_goal_runtime import refs_snapshot,validate_refs

from lab_generate_skill.gitlab_native_csv_probe import auth_backup,restore_auth_metadata,protected_snapshot_session

VERSION='gitlab-next-source-ordinary-cpu-v1'

def read(p):return json.loads(Path(p).read_text())

def artifact(directory,name):
 root=Path(directory).resolve();p=root/name
 if not p.is_file()or p.is_symlink()or not p.resolve().is_relative_to(root):raise ValueError('Complete original private artifact required: '+name)
 return p

def enabled(c):
 binding(c)
 if c.get('family')!='gitlab_next_native' or c.get('public_parameters',{}).get('operation')not in ('switch_account','blank_description','whats_new'):
  raise ValueError('Explicit supported native account/process/release operation required')
 component.enabled(c)
 return True

def public_goal(c):
 enabled(c);public.public_input(c)
 return public.append_parameters(c,c['goal'])

def expectations(c):
 enabled(c)
 names={'initial_no_op':'failure','positive':'success','wrong_object':'failure','404':'failure','login':'failure'}
 if c['public_parameters']['operation']=='switch_account':names.update(signed_out_only='failure',same_account_relogin='failure',filled_unsaved='failure')
 elif c['public_parameters']['operation']in('last_closed','literal_projects','blank_description'):names['wrong_answer']='failure'
 return names

class Hooks:
 def __init__(self,c,private,directory,*,proof=None,proof_session=None):
  component.enabled(c);self.contract=deepcopy(c);self.private=deepcopy(private);self.directory=Path(directory)
  if proof is None:raise ValueError("Complete native admission proof required")
  elif proof_session is not None:
   from .native_proof_session import NativeProofSession
   if not isinstance(proof_session,NativeProofSession):raise ValueError('Verified native proof session required')
   proof_session.reuse_verified(c,proof)
  else:require_two_cold(c,proof['cycles'],proof['directories'])
  native.validate_reference(private,c['public_parameters'])
  self.proof=proof;self.site=self.context=self.page=None;self.listener=None;self.closed=False;self.chat=None;self.events=[];self.captures=[];self.issued=[];self.pending=None;self.prepared=self.scored=False

  self.terminal = None; self.current_page = None; self.closed = False
 def prepare(self,site,username):
  if self.prepared or site.domain!='gitlab':raise ValueError('One real ordinary native preparation required')
  self.site=site;self.username=username;self.cold,self.before,self.effects=shared.initialize_baseline(site,self.directory/'cache-initialization')
  full_snapshot(self.before);self.refs_before=refs_snapshot(site);self.auth=[auth_backup(site,username)]
  if self.contract['public_parameters']['operation']=='switch_account':
   self.auth.append(auth_backup(site,self.contract['public_parameters']['target_username']))
   if [x['id']for x in self.auth]!=[self.private['initial_id'],self.private['target_id']]:raise ValueError('Qualified original/target native accounts differ')
  if self.proof is not None:
   initial=self.proof['cycles'][0]['controls']['initial_no_op']
   if (self.cold,self.before,self.refs_before)!=(initial['native_before_initialization'],initial['protected_before'],initial['refs_before']):raise ValueError('Normal full native baseline differs from proof')
  self.prepared=True;self.events.append({'kind':'prepare'})
 def attach(self,context):
  if not self.prepared or self.context is not None:raise ValueError('One prepared native browser context required')
  self.context=context
  def request(r):
   u=urlsplit(r.url)
   if u.netloc==urlsplit(self.site.url).netloc and u.path in('/users/sign_in','/users/sign_out'):
    # Never serialize request bodies, cookies, passwords or headers.
    self.events.append({'kind':'native_request','method':r.method,'path':u.path})
  self.listener=request;context.on('request',request);self.events.append({'kind':'attach'})
 def observe_initial(self,page):
  page_lifetime.live_page(self, page, initial=True)
  if self.page is not None or page.context is not self.context or page.url!=self.site.url+self.contract['start_path']:raise ValueError('Exact original or explicitly revised start required')
  self.page=page;self.events.append({'kind':'observe_initial'});self.record(page)
 def record(self,page):
  page_lifetime.live_page(self, page)
  v=component.capture(page);self.captures.append(v);self.pending=v
  self.events.append({'kind':'capture','account_id':v['account_id'],'path':urlsplit(v['url']).path});self.events.append({'kind':'record'})
 def acknowledge_issued(self,actual_ax):
  if not isinstance(actual_ax,str)or not actual_ax:raise ValueError('Actual issued AX required')
  if self.pending is not None:
    self.issued.append({'capture':deepcopy(self.pending),'actual_issued_ax':actual_ax,'actual_issued_ax_sha256':hashlib.sha256(actual_ax.encode()).hexdigest()});self.pending=None
 def capture_chat(self,messages):
  if self.chat is not None or not isinstance(messages,list)or any(not isinstance(m,dict)or not {'role','timestamp','message'}<=set(m)or m['role']not in('user','user_image','assistant','infeasible')or not isinstance(m['message'],str)or type(m['timestamp'])not in(int,float)for m in messages):raise ValueError('Complete actual ordinary BrowserGym chat required')
  self.chat=deepcopy(messages);write(self.directory/'terminal-chat.json',self.chat)
  self.events.append({'kind':'capture_chat','messages':len(messages)})
 def capture_terminal(self,page,terminal):
  page_lifetime.terminal_page(self, page, terminal)
  if self.chat is None:raise ValueError('Actual ordinary chat was not captured before terminal scoring')
  replies=[m['message']for m in self.chat if m['role']=='assistant']
  terminal['answer']=replies[-1]if replies else''
  terminal['gitlab_next_capture']=component.capture(page);self.terminal=terminal;self.events.append({'kind':'capture_terminal'})
  write(self.directory/'terminal-next-native.json',terminal['gitlab_next_capture'])
 def close(self):
  if self.closed:return
  self.closed=True
  if self.context is not None and self.listener is not None:
   self.context.remove_listener('request',self.listener)
   self.listener=None
 def score_terminal(self,site,terminal,*,runtime_error=None):
  score_complete = page_lifetime.score_bound(self, site, terminal, runtime_error)
  self.scored=True;self.events.append({'kind':'score_terminal'})
  # Restore only each independently identified user's exact pre-login AUTH
  # columns. Name/password/role and every other user remain protected.
  for a in self.auth:restore_auth_metadata(site,a)
  after=protected_snapshot_session(site,self.directory/'full16-after-progress.jsonl');full_snapshot(after);refs_after=refs_snapshot(site)
  integrity=self.before==after and self.refs_before==refs_after and all(auth_backup(site,n)==a for n,a in zip([self.username]+([self.contract['public_parameters']['target_username']]if len(self.auth)==2 else[]),self.auth))
  j=component.evaluate(self.contract,self.private,terminal,self.captures,self.events,site.url) if score_complete else None
  if not score_complete or not integrity:j={'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':'Runtime or complete protected native state mismatch'}
  self.receipt={'version':VERSION,'contract':self.contract,'source_binding':binding(self.contract),'private_reference':self.private,'site_origin':site.url,
   'native_before_initialization':self.cold,'native_initialization_effects':self.effects,'protected_before':self.before,'protected_after':after,'refs_before':self.refs_before,'refs_after':refs_after,
   'native_auth_baselines':self.auth,'terminal':deepcopy(terminal),'actual_chat':self.chat,'captures':self.captures,'issued_observations':self.issued,'events':self.events,'judgment':j,'integrity':integrity,
   'actor_attempts':0,'api_calls':0,'normal_gate_passed':False,'training_admitted':False}
  write(self.directory/'native-private-receipt.json',self.receipt);return j,integrity

def require_two_cold(case,cycles,folders):
 from . import gitlab_next_runtime as original_driver
 from .description_revision_qualification import qualify
 if not isinstance(cycles,list) or len(cycles)!=2:raise ValueError('Two exact original cycles required')
 original=cycles[0]['contract']
 value=qualify(original,case,cycles,folders,original_driver=original_driver,candidate_component=component)
 return dict(value,passed=True,source_task_id=case['source_task_id'],cycles=2,normal_gate_passed=False)

from . import native_artifact_page_lifetime as page_lifetime
