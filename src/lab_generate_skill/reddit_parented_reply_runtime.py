"""Candidate public parented replies through the ordinary terminal hook slot.

Only observations and terminal private checks occur in hooks. CPU controls use
an explicit private first-control constructor; normal construction always
requires actual source-bound two-cold evidence. No actor actions are injected.
"""
from copy import deepcopy
import hashlib,json,re
from pathlib import Path
from urllib.parse import urlsplit
from lab_generate_skill.io_utils import atomic_write_json
from lab_generate_skill.source_revision_binding import binding,require_source_binding
from lab_generate_skill.reddit_final_read_runtime import METHODS
from lab_generate_skill.site_navigation_rules import valid_initial_page
from lab_generate_skill.reddit_search import read_search_page
from . import reddit_parented_reply as rule
from . import reddit_parented_reply_native as native

VERSION='reddit-parented-reply-public-normal-v2'
AUTHORIZED_TARGET_WRITES=True

READ=r'''() => {
 const visible=e=>{if(!e||!e.isConnected||![...e.getClientRects()].some(r=>r.width&&r.height))return false;for(let n=e;n;n=n.parentElement){const s=getComputedStyle(n);if(s.display==='none'||s.visibility==='hidden'||s.visibility==='collapse'||Number(s.opacity)===0)return false;}return true;};
 const sameOwn=(root,s)=>[...root.querySelectorAll(s)].filter(e=>e.closest('article.comment')===root);
 const comments=[...document.querySelectorAll('#main article.comment')].map(a=>{
  const link=sameOwn(a,'a.comment__permalink')[0],u=link?new URL(link.href):null,m=u?.pathname.match(/^\/f\/([^/]+)\/(\d+)\/[^/]+\/comment\/(\d+)$/);
  const user=sameOwn(a,'.comment__info a[href*="/user/"]')[0];
  return {id:Number((a.id.match(/^comment_(\d+)$/)||[])[1])||null,submission_id:m?Number(m[2]):null,author:user?decodeURIComponent(new URL(user.href).pathname.slice('/user/'.length)):null,marker_bids:[link?.getAttribute('bid'),...sameOwn(a,'a.comment__reply-link').map(e=>e.getAttribute('bid'))].filter(Boolean),visible:visible(a)&&a.classList.contains('comment--visibility-visible'),url:link?.href||null};
 });
 const submissions=[...document.querySelectorAll('#main a.submission__link')].map(a=>{const m=new URL(a.href).pathname.match(/^\/f\/([^/]+)\/(\d+)(?:\/|$)/);return {id:m?Number(m[2]):null,title:a.innerText.trim(),bid:a.getAttribute('bid'),url:a.href,visible:visible(a)};});
 return {url:location.href,comments,submissions,search_query:document.querySelector('input#query')?.value||null,capture_truncated:false};
}'''

def enabled(c):
 if 'parented_reply'not in c:return False
 rule.validate_contract(c)
 if any(c.get(k)for k in ('reddit_search_completion','reddit_original_reading','reddit_maximum_query','query','preferences','explicit_submission','submission','membership','wiki','vote')):
  raise ValueError('One isolated native reply lifecycle required')
 return True

def fields(c):enabled(c);return []
def public_goal(c):
 enabled(c)
 return c['goal']+'\nPublic task parameters: '+json.dumps(c['public_parameters'],sort_keys=True,ensure_ascii=False)
def require_original_binding(c,original,inventory):return require_source_binding(c,original,inventory,domain='reddit')
def provenance():
 from lab_generate_skill import source_revision_binding,reddit_search
 from . import reddit_fresh_capture_handoff
 return {'lifecycle_methods':METHODS,'runtime_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
  'rule_sha256':hashlib.sha256(Path(rule.__file__).read_bytes()).hexdigest(),
  'native_reader_sha256':hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest(),
  'native_asset_sha256':native.ASSET_SHA,'source_binding_sha256':hashlib.sha256(Path(source_revision_binding.__file__).read_bytes()).hexdigest(),
  'native_search_sha256':hashlib.sha256(Path(reddit_search.__file__).read_bytes()).hexdigest(),
  'same_boundary_handoff_sha256':hashlib.sha256(Path(reddit_fresh_capture_handoff.__file__).read_bytes()).hexdigest()}

def validate_initial_state(c,value):
 enabled(c)
 expected={'target','threads','matching_posts','search_rows','reply_notification_recipients','recipient_user_rows','recipient_block_rows','user_id','username','complete13','known_comment_ranges','thread_counter_references','reply_body'}
 if not isinstance(value,dict)or set(value)!=expected or not rule.positive_int(value['user_id'])or not isinstance(value['username'],str)or value['reply_body']!=c['parented_reply']['reply_body']:
  raise ValueError('Complete public-reply initial private reference required')
 rule.validate_snapshot(value['complete13']);rule.validate_ranges(value['known_comment_ranges'])
 if value['known_comment_ranges']!=value['complete13']['known_comment_ranges']:raise ValueError('Complete original comment identity coverage differs')
 target=rule.resolve_reference(c,value['target']['parents'],value['matching_posts'],value['search_rows'])
 if target!=value['target']or {r['id']for r in value['threads']}!=set(target['submission_ids']):raise ValueError('Bound private native target set differs')
 if set(value['thread_counter_references'])!={str(x)for x in target['submission_ids']}or set(value['reply_notification_recipients'])!={str(x['id'])for x in target['parents']}:
  raise ValueError('Every target native counter/notification recipient must be bound before actions')
 if any(value['thread_counter_references'][str(r['id'])]['count']!=r['comment_count']for r in value['threads']):raise ValueError('Complete native visible-comment counts differ')
 return deepcopy(value)

def require_admission(c,p):
 enabled(c)
 if not isinstance(p,dict)or p.get('version')!=rule.ADMISSION_VERSION or p.get('fingerprint')!=rule.fingerprint(c)or p.get('source_binding')!=binding(c)or p.get('provenance')!=provenance()or p.get('actor_attempts')!=0 or p.get('api_calls')!=0:
  raise ValueError('Fresh exact public-reply source-bound proof required')
 cycles=p.get('cycles',[])
 if len(cycles)!=2 or any(not isinstance(r.get('fresh_instance_id'),str)or not re.fullmatch('[0-9a-f]{64}',r['fresh_instance_id'])for r in cycles)or len({r['fresh_instance_id']for r in cycles})!=2:
  raise ValueError('Two distinct actual cold native instances required')
 baseline=None
 for cycle in cycles:
  initial=validate_initial_state(c,cycle['private_reference'])
  if baseline is not None and baseline!=initial:raise ValueError('Exact private baseline differs between cold instances')
  baseline=initial
  rule.validate_snapshot(cycle['complete13_before']);rule.validate_snapshot(cycle['complete13_after'])
  if cycle['group_final_seal']is not True or native.stable_snapshot(cycle['complete13_before'])!=initial['complete13']or native.stable_snapshot(cycle['complete13_after'])!=initial['complete13']or cycle['selected_before']!=cycle['selected_after']:
   raise ValueError('Complete13 plus supplemental native two-cold reset required')
  controls=cycle['controls']
  if set(controls)!=set(rule.expected_controls(c)):raise ValueError('All actual reply positive/negative boundaries required')
  for name,record in controls.items():
   if record.get('provenance')!=provenance()or record.get('lifecycle')!=METHODS[:-1]or record.get('actual_normal_browsergym_session')is not True or record.get('bound_original_start_restored')is not True or record.get('guard_scope')!='normal_source_full13_plus_notifications_before_after':
    raise ValueError('Actual normal method-chain private controls required')
   before=record['actual_complete13_before'];after=record['actual_complete13_after']
   rule.validate_snapshot(before);rule.validate_snapshot(after)
   if native.stable_snapshot(before)!=initial['complete13']:raise ValueError('Each actual preparation must freshly cover full13 and notifications')
   integrity=rule.protected_integrity(before,after,initial=initial,added=after['new_comments'],votes=after['new_comment_votes'],threads=after['threads'])
   if integrity is not record['integrity']:raise ValueError('Actual private guard cannot be reproduced')
   final={'added':after['new_comments'],'integrity':integrity}
   reproduced=rule.evaluate(c,record['terminal'],initial,final,site_origin=record['site_origin'],public={'observations':record['observations'],'observed_comments':record['public_observed_comments']})
   reproduced['version']=VERSION
   if record['judgment']!=reproduced or reproduced['status']!=rule.expected_controls(c)[name]:raise ValueError('Actual public reply terminal control differs')
   if record.get('reset_verified')is not True or record.get('reset_complete13')!=initial['complete13']:raise ValueError('Every mutating control must prove complete restoration')
 return deepcopy(baseline)

class _ParentedReplyHooks:
 def __init__(self,c,private,directory,*,fresh_capture=None):
  enabled(c);self.contract=deepcopy(c);self.expected=validate_initial_state(c,private);self.directory=Path(directory)
  self.directory.mkdir(parents=True,exist_ok=True);self.site=self.context=self.initial=self.pending=None
  self.prepared=self.scored=False;self.events=[];self.observations=[];self.observed_comments=[];self.fresh_capture=fresh_capture;self.before_handoff=None
 def prepare(self,site,username):
  if self.prepared or site.domain!='reddit':raise ValueError('One actual independent native preparation required')
  native.preflight_assets(site)
  capture=None
  if self.fresh_capture is not None:
   from .reddit_fresh_capture_handoff import FreshCapture
   if not isinstance(self.fresh_capture,FreshCapture):raise ValueError('Typed one-use complete native capture required')
   capture,self.before_handoff=self.fresh_capture.consume(site,self.contract,username)
   atomic_write_json(self.directory/'prepare'/'fresh-full13-handoff.json',self.before_handoff)
  current,before=native.initial_state(site,self.contract,username,self.directory/'prepare',return_capture=True,captured_before=capture)
  if current!=self.expected:raise ValueError('Actual full13/supplement/private reference differs from control baseline')
  self.before=before
  if native.stable_snapshot(self.before)!=current['complete13']:raise ValueError('Private reference changed before ordinary prepare')
  self.site,self.username=site,username;self.prepared=True;self.events.append('prepare')
  atomic_write_json(self.directory/'actual-complete13-before.json',self.before)
 def attach(self,context):
  if not self.prepared or self.context is not None:raise ValueError('One prepared actual context required')
  self.context=context;self.events.append('attach')
 def observe_initial(self,page):
  if self.initial is not None or page.context is not self.context or rule.path(page.url)!=self.contract['start_path']:raise ValueError('Exact declared first start required')
  self.initial=page;self.events.append('observe_initial')
 def record(self,page):
  if self.scored or page is not self.initial or page.context is not self.context:raise ValueError('Only current bound ordinary page observations allowed')
  from probe_content_sites import capture_current
  public=page.evaluate(READ);health=capture_current(page,'reddit')
  self.pending={'native':public,'page':health}
  if urlsplit(page.url).path=='/search':self.pending['search']=read_search_page(page)
  self.events.append('record')
 def acknowledge_issued(self,actual_ax):
  if not isinstance(actual_ax,str)or self.pending is None:raise ValueError('Actual issued actor observation required')
  current=deepcopy(self.pending)|{'actual_issued_ax':actual_ax}
  if not self.observations or current!=self.observations[-1]:
   self.observations.append(current);self.observed_comments.extend(deepcopy(current['native']['comments']))
  self.events.append('acknowledge_issued')
 def capture_terminal(self,page,terminal):
  if self.scored or page is not self.initial or page.context is not self.context or terminal.get('url')!=page.url:raise ValueError('One actual bound native terminal required')
  self.terminal=deepcopy(terminal);self.events.append('capture_terminal')
 def provide_trace(self,trace):
  if not isinstance(trace,dict):raise ValueError('Actual rollout trace required')
  self.trace=deepcopy(trace);self.events.append('provide_trace')
 def score_terminal(self,site,terminal,*,runtime_error=None):
  if self.scored or site is not self.site or terminal!=getattr(self,'terminal',None):raise ValueError('One bound terminal-only scoring required')
  self.scored=True;self.events.append('score_terminal');after=None;integrity=False
  try:
   candidate=native.new_candidate(site,self.expected)
   after=native.snapshot(site,self.directory/'terminal',initial=self.expected,candidate=candidate)
   integrity=rule.protected_integrity(self.before,after,initial=self.expected,added=after['new_comments'],votes=after['new_comment_votes'],threads=after['threads'])
   j=rule.evaluate(self.contract,terminal,self.expected,{'added':after['new_comments'],'integrity':integrity},site_origin=site.url,public={'observations':self.observations,'observed_comments':self.observed_comments},runtime_error=runtime_error)
  except Exception as error:
   j={'version':rule.VERSION,'status':'unknown','reward':None,'checks':{},'reason':'Complete native reply capture unavailable'}
   atomic_write_json(self.directory/'private-capture-error.json',{'type':type(error).__name__,'message':str(error)[:800]})
  j['version']=VERSION
  self.receipt={'lifecycle':list(dict.fromkeys(self.events)),'provenance':provenance(),'site_origin':site.url,'observations':deepcopy(self.observations),'terminal':deepcopy(terminal),'judgment':j,'integrity':integrity,'guard_scope':'normal_source_full13_plus_notifications_before_after','actual_complete13_before':deepcopy(self.before),'actual_complete13_after':deepcopy(after),'public_observed_comments':deepcopy(self.observed_comments)}
  if self.before_handoff is not None:self.receipt['before_capture_handoff']=deepcopy(self.before_handoff)
  atomic_write_json(self.directory/'normal-native-parented-reply-receipt.json',self.receipt)
  return j,integrity
 def close(self):pass

class ParentedReplyHooks(_ParentedReplyHooks):
 def __init__(self,c,proof,directory):super().__init__(c,require_admission(c,proof),directory)

def create_cpu_hooks(c,private,directory,*,cpu_control_only=False,fresh_capture=None):
 if cpu_control_only is not True:raise ValueError('Unadmitted constructor is for native CPU controls only')
 from lab_generate_skill.runtime_watchdog import require_watchdog
 require_watchdog()
 return _ParentedReplyHooks(c,private,directory,fresh_capture=fresh_capture)

def feedback(j):
 return {'status':j['status'],'reward':j['reward'],'reason':j.get('reason'),'checks':{k:v for k,v in j.get('checks',{}).items()if type(v)is bool},'private_reference_values_provided':False,'action_sequence_provided':False}
