"""Shared terminal-only original/explicit reading lifecycle for final Reddit.

The private CPU constructor executes the same methods. Its optional measured
cold-group epoch additionally requires a final whole-group seal. Both private
CPU controls and normal actors freshly scan full13 at each actual preparation
and terminal; a transient foreign mutation cannot be hidden by later restore. No checks run during action decisions and no values are
injected into the actor observations.
"""
from copy import deepcopy
import hashlib,json,re
from pathlib import Path
from urllib.parse import urlsplit
from . import reddit_original_goal_reading as original
from . import reddit_maximum_query as maximum
from . import reddit_native_read_protection as protection
from . import reddit_issued_record as issued_record
from .reddit_native_read_runtime import validate_complete_snapshot
from .source_revision_binding import binding,fingerprint,require_source_binding
from .site_navigation_rules import valid_initial_page
from .io_utils import atomic_write_json
VERSION='reddit-final-native-reading-runtime-v2';PROOF='reddit-final-native-reading-two-cold-v2'
SHA=re.compile('[0-9a-f]{64}')
METHODS=['prepare','attach','observe_initial','record','acknowledge_issued','capture_terminal','provide_trace','score_terminal','close']
def enabled(c):
 if 'reddit_original_reading'not in c and'reddit_maximum_query'not in c:return False
 if ('reddit_original_reading'in c)==('reddit_maximum_query'in c)or c.get('domain')!='reddit'or c.get('eligible_for_training')is not False or c.get('heldout_quarantine')is not False:raise ValueError('One original/explicit final native reading family required')
 binding(c)
 if'reddit_original_reading'in c:
  if c['reddit_original_reading'].get('kind')not in original.KINDS:raise ValueError('Supported original public reading family required')
 else:maximum.enabled(c)
 return True
def fields(c):
 enabled(c)
 if'reddit_maximum_query'in c:return maximum.fields(c)or[]
 return ['exists']if c['reddit_original_reading']['kind']=='native_forum_existence'else[]
def public_goal(c):
 keys=fields(c)
 if not keys:return c['goal']
 from .browser_prompt_contract import query_finish_instruction
 shape='\nThe exists field must be a JSON boolean (true or false).'if keys==['exists']else''
 return c['goal']+'\n'+query_finish_instruction(keys)+shape
def require_original_binding(c,original_c,inventory):return require_source_binding(c,original_c,inventory,domain='reddit')
def provenance():return {'lifecycle_methods':METHODS,'runtime_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'original_reading_sha256':hashlib.sha256(Path(original.__file__).read_bytes()).hexdigest(),'maximum_reading_sha256':hashlib.sha256(Path(maximum.__file__).read_bytes()).hexdigest(),'complete13_protection_sha256':hashlib.sha256(Path(protection.__file__).read_bytes()).hexdigest(),'issued_record_sha256':hashlib.sha256(Path(issued_record.__file__).read_bytes()).hexdigest()}
def ref(site,c,username):return maximum.reference(site,c,username)if'reddit_maximum_query'in c else original.reference(site,c,username)
def _path(value):
 u=urlsplit(value);return(u.path or'/')+('?' +u.query if u.query else'')+('#'+u.fragment if u.fragment else'')
def require_rule_only_origin(controls,name,record):
 if record.get('rule_only')is True:
  base=controls.get(record.get('reused_actual_terminal_control'))
  if not isinstance(base,dict)or base.get('rule_only')is True or record.get('actual_original_terminal_answer')!=base.get('answer')or any(record.get(k)!=base.get(k)for k in('lifecycle','provenance','site_origin','observations','snapshots','terminal','integrity','actual_complete13_before','actual_complete13_after','guard_scope','actual_actions','normal_public_requests')):raise ValueError('Rule-only alternative must reuse the exact actual terminal and complete native guard')
  if name not in('wrong_answer','unobserved_correct_answer'):raise ValueError('Only declared answer perturbations are rule-only controls')
def require_admission(c,p):
 from . import reddit_reading_proof_replay as replay
 if isinstance(p,dict) and p.get('version')==replay.VERSION:
  return replay.require_replayed(c,p)
 return _validate_admission(c,p,provenance())
def _validate_admission(c,p,executed_provenance):
 # The archived path retains its executed provenance verbatim. Only the
 # explicit replay adapter may select a recognized historical dependency set.
 enabled(c)
 if not isinstance(p,dict)or p.get('version')!=PROOF or p.get('fingerprint')!=fingerprint(c)or p.get('source_binding')!=binding(c)or p.get('provenance')!=executed_provenance or p.get('actor_attempts')!=0 or p.get('api_calls')!=0:raise ValueError('Actual final-native same-method two-cold proof required')
 cycles=p.get('cycles');ids=[r.get('fresh_instance_id')for r in cycles]if isinstance(cycles,list)else[]
 if len(ids)!=2 or any(not isinstance(x,str)or not SHA.fullmatch(x)for x in ids)or len(set(ids))!=2:raise ValueError('Two distinct cold native instances required')
 before=None;private=None
 for cycle in cycles:
  baseline=validate_complete_snapshot(cycle.get('complete13_before'))
  if cycle.get('group_final_seal')is not True or validate_complete_snapshot(cycle.get('complete13_after'))!=baseline or cycle.get('selected_before')!=cycle.get('selected_after'):raise ValueError('Full actual cold-group restoration required')
  if before is not None and baseline!=before or private is not None and private!=cycle['private_reference']:raise ValueError('Actual cold scope/reference differs')
  before=baseline;private=cycle['private_reference']
  controls=cycle.get('controls')
  if not isinstance(controls,dict)or not {'initial_no_op','positive','wrong_target','404','login'}<=set(controls):raise ValueError('Actual normal positive and negative controls required')
  for name,record in controls.items():
   require_rule_only_origin(controls,name,record)
   if record.get('integrity')is not True or record.get('lifecycle')!=METHODS[:-1]or record.get('provenance')!=executed_provenance or record.get('actual_normal_browsergym_session')is not True or record.get('bound_original_start_restored')is not True:raise ValueError('Actual normal BrowserGym same-hook lifecycle required')
   if record.get('guard_scope')!='normal_source_full13_before_after'or validate_complete_snapshot(record.get('actual_complete13_before'))!=baseline or validate_complete_snapshot(record.get('actual_complete13_after'))!=baseline:raise ValueError('Actual fresh complete13 guard at each normal preparation and terminal required')
   expected='success'if name=='positive'else'failure'
   if record.get('judgment',{}).get('status')!=expected:raise ValueError('Actual control result does not match boundary')
   reproduced=evaluate(c,private,record['observations'],record['snapshots'],record['terminal'],record['answer'],site_origin=record['site_origin'])
   if record['judgment']!=reproduced:raise ValueError('Frozen normal terminal control cannot be reproduced')
 return deepcopy(before),deepcopy(private)
def evaluate(c,private,observations,snapshots,terminal,answer,*,site_origin):
 if'reddit_maximum_query'in c:return maximum.evaluate(c,private,snapshots,terminal,answer,origin=site_origin)
 return original.evaluate(c,observations,private,site_origin=site_origin,answer=answer)
class ColdReadEpoch:
 """Additional complete group seal; never substitutes individual fresh guards."""
 def __init__(self,site,baseline,selected):self.site=site;self.baseline=deepcopy(validate_complete_snapshot(baseline));self.selected=selected;self.closed=False;self.seal=None
 def require(self,site):
  if self.closed or site is not self.site or site.fingerprint()!=self.selected:raise ValueError('Only live measured untouched cold read group required')
  return deepcopy(self.baseline)
 def close(self,after,selected):
  self.closed=True;self.seal=validate_complete_snapshot(after)==self.baseline and selected==self.selected;return self.seal
class _ReadingHooks:
 def __init__(self,c,baseline,private,directory,*,epoch=None):
  enabled(c);self.contract=deepcopy(c);self.baseline=deepcopy(validate_complete_snapshot(baseline));self.expected=deepcopy(private);self.directory=Path(directory);self.epoch=epoch;self.prepared=False;self.context=None;self.initial=None;self.site=None;self.scored=False;self.events=[];self.observations=[];self.snapshots=[];self.pending=None;self.answer=None
 def prepare(self,site,username):
  if self.prepared or site.domain!='reddit':raise ValueError('One actual normal native reset required')
  if self.epoch is not None:self.epoch.require(site)
  current=protection.complete_snapshot(site,self.directory/'full13-before-progress.jsonl')
  self.actual_before=deepcopy(current)
  atomic_write_json(self.directory/'actual-complete13-before.json',current)
  private=ref(site,self.contract,username)
  if current!=self.baseline or private!=self.expected:raise ValueError('Actual full native before/reference differs')
  self.site,self.username,self.selected=site,username,site.fingerprint();self.prepared=True;self.events.append('prepare')
 def attach(self,context):
  if not self.prepared or self.context is not None:raise ValueError('One source-local actual browser context required')
  self.context=context;self.events.append('attach')
 def observe_initial(self,page):
  if page.context is not self.context or self.initial is not None or _path(page.url)!=self.contract['start_path']:raise ValueError('Original or explicit declared start required')
  self.initial=page;self.events.append('observe_initial')
 def record(self,page):
  if self.scored or page is not self.initial or page.context is not self.context:raise ValueError('Only bound actual normal rollout Page observations required')
  from probe_content_sites import capture_current
  health=capture_current(page,'reddit');native=original.read(page,health)
  self.pending={'original':native,'maximum':page.evaluate(maximum.READ)};self.events.append('record')
 def acknowledge_issued(self,actual_ax):
  if not isinstance(actual_ax,str)or self.pending is None:raise ValueError('Actual issued normal actor observation required')
  candidate=self.pending
  # Viewport pruning may remove a node: maximum reader independently checks
  # every native record label/identity against the actually issued text.
  issued=deepcopy(candidate['original']);issued['actual_issued_ax']=actual_ax
  snapshot=candidate['maximum']|{'record_source':'actual_actor_request','issued_ax':actual_ax}
  if not self.observations or self.observations[-1]!=issued or self.snapshots[-1]!=snapshot:
   self.observations.append(issued);self.snapshots.append(snapshot)
  self.events.append('acknowledge_issued')
 def capture_terminal(self,page,terminal):
  if self.scored or page is not self.initial or page.context is not self.context or terminal.get('url')!=page.url:raise ValueError('One bound actual native terminal document required')
  self.terminal=deepcopy(terminal);self.events.append('capture_terminal')
 def provide_trace(self,trace):
  if not isinstance(trace,dict):raise ValueError('Actual normal rollout trace required')
  self.trace=deepcopy(trace)
  from .admin_pilot import final_answer
  self.answer=final_answer(trace);self.events.append('provide_trace')
 def score_terminal(self,site,terminal,*,runtime_error=None):
  if self.scored or site is not self.site or terminal!=getattr(self,'terminal',None):raise ValueError('Only bound terminal-only native scoring required')
  self.scored=True;self.events.append('score_terminal')
  result=evaluate(self.contract,self.expected,self.observations,self.snapshots,terminal,self.answer,site_origin=site.url)
  after=protection.complete_snapshot(site,self.directory/'full13-after-progress.jsonl')
  atomic_write_json(self.directory/'actual-complete13-after.json',after)
  integrity=after==self.baseline and site.fingerprint()==self.selected and ref(site,self.contract,self.username)==self.expected
  if runtime_error:result={'version':VERSION,'status':'unknown','reward':None,'checks':{}}
  elif not integrity:result={'version':VERSION,'status':'failure','reward':0.0,'checks':{'complete_native_integrity':False}}
  self.receipt={'lifecycle':list(dict.fromkeys(self.events)),'provenance':provenance(),'site_origin':site.url,'observations':deepcopy(self.observations),'snapshots':deepcopy(self.snapshots),'terminal':deepcopy(terminal),'answer':self.answer,'judgment':result,'integrity':integrity,'guard_scope':'normal_source_full13_before_after','actual_complete13_before':deepcopy(self.actual_before),'actual_complete13_after':deepcopy(after)}
  atomic_write_json(self.directory/'normal-native-reading-receipt.json',self.receipt);return result,integrity
 def close(self):pass
class FinalReadingHooks(_ReadingHooks):
 def __init__(self,c,proof,directory):
  baseline,private=require_admission(c,proof);super().__init__(c,baseline,private,directory)
def feedback(judgment):return {'status':judgment['status'],'reward':judgment['reward'],'checks':{k:v for k,v in judgment['checks'].items()if type(v)is bool},'private_reference_values_provided':False,'action_sequence_provided':False}
