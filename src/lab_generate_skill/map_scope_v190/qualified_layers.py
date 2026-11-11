"""Public-goal revision around unchanged original native overlay lifecycle."""
from pathlib import Path
from copy import deepcopy
import hashlib,json
from lab_generate_skill import map_native_layer_runtime as native
from lab_generate_skill.map_layer_scope_revision import validate,verify_reusable_native_controls

def read(ref):
 p=Path(ref['path']);raw=p.read_bytes()
 if not p.is_absolute()or p.is_symlink()or hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Pinned reviewed scope evidence changed')
 return json.loads(raw)
class Hooks:
 def __init__(self,c,proof,directory):
  self.native=native.NativeLayerHooks(validate(c),proof,directory);self.site=self.context=None
 def prepare(self,site,username):
  if username is not None or self.site is not None:raise ValueError('One anonymous map lifecycle required')
  self.native.prepare(site);self.site=site
 def attach(self,context):
  if self.context is not None:raise ValueError('One private context required')
  self.context=context
 def initialize_browser(self,page):
  if page.context is not self.context:raise ValueError('Observed page differs from private context')
  self.native.attach(page,self.site.url)
 def observe_initial(self,page):return self.native.observe_initial(page)
 def record(self,page):return self.native.record(page)
 def capture_terminal(self,page,terminal):return self.native.terminal(page,terminal)
 def close(self):return self.native.close()
 def score_terminal(self,site,terminal,*,runtime_error=None):
  if site is not self.site:raise ValueError('Terminal site differs')
  judgment=self.native.evaluate(site,terminal,runtime_error=runtime_error)
  try:site.reset_guard.require_unchanged();integrity=site.fingerprint()==self.native.native['baseline']
  except Exception:integrity=False
  return judgment,integrity

class Adapter:
 FEEDBACK_VERSIONS=(native.VERSION,)
 AUTHORIZED_TARGET_WRITES=False
 def __init__(self,plan):
  self.plan=plan;self.proof=read(plan['native_proof']);self.review=read(plan['input_review']);self.candidates={}
  assert self.review['passed']and self.review['first_native_observations_reconstructed']==6 and self.review['new_actual_actor_requests']==0
  for ref in self.review['rows']:
   item=read(ref['evidence']);c=item['candidate'];original=validate(c);sid=c['source_task_id']
   assert item['new_task_id']==c['task_id']and item['new_model_request_sent']is False and item['historical_actor_result_reused']is False
   assert item['native_predicate_reuse']==verify_reusable_native_controls(c,self.proof)
   assert json.loads(item['messages'][-1]['content'])['goal']==c['goal']and not item['observation_budget']['truncated']
   assert item['browser_task']['goal']==c['goal']and item['browser_task']['task_id']==c['task_id']
   self.candidates[sid]=c
  assert len(self.candidates)==6
 def enabled(self,c):return c.get('version')=='map-local-overlay-public-scope-v1'and c.get('source_task_id')in self.candidates
 def canonical(self,c):
  value={k:v for k,v in c.items()if k!='admission_result'}
  if value!=self.candidates.get(c.get('source_task_id')):raise ValueError('Exact new overlay public task identity required')
  return deepcopy(value)
 def require_admission(self,c,descriptor):
  c=self.canonical(c)
  if descriptor!=dict(version='public-overlay-ordinary-admission-v190',source_task_id=c['source_task_id'],task_id=c['task_id'],native_proof=self.plan['native_proof'],input_review=self.plan['input_review']):raise ValueError('Exact reviewed overlay descriptor required')
  if read(self.plan['native_proof'])!=self.proof:raise ValueError('Native control proof changed')
  return native.require_admission(validate(c),self.proof)
 def require_original_binding(self,c,original,inventory):
  c=self.canonical(c)
  if c!=original:raise ValueError('New public task changed after input qualification')
  return native.require_original_binding(validate(c),validate(c),inventory)
 def NativeReadHooks(self,c,proof,directory):
  self.require_admission(c,proof);return Hooks(self.canonical(c),self.proof,directory)
 def public_goal(self,c):return self.canonical(c)['goal']
 def fields(self,c):self.canonical(c);return []
 def feedback(self,judgment):return native.feedback(judgment)
