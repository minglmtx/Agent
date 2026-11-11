"""Exact search-only source using retained native controls and public inputs."""
from pathlib import Path
from copy import deepcopy
import hashlib,json
from .archive_reader import unpack,verified
from .evaluate import evaluate,VERSION,SOURCE
from .search_hooks import SearchHooks
from lab_generate_skill.source_revision_binding import binding,require_source_binding
from lab_generate_skill.map_route_normal_capture import fingerprint
from lab_generate_skill.config import load_settings
from lab_generate_skill.llm import TransformersChatBackend
from lab_generate_skill.runtime_profile import actor_protocol
from lab_generate_skill.observation_budget import fit_actor_messages
from transformers import AutoTokenizer
load=lambda p:json.loads(Path(p).read_text())

class Adapter:
 FEEDBACK_VERSIONS=(VERSION,)
 AUTHORIZED_TARGET_WRITES=False
 def __init__(self,config,*,project,work):
  self.config=deepcopy(config);self.identities={};self.project=Path(project)
  self.c=self.read(config['contract']);binding(self.c)
  self.inventory=self.read(config['inventory'])
  require_source_binding(self.c,self.c,self.inventory,domain='map')
  self.reference=self.read(config['reference'])
  self.review=self.read(config['review']);self.descriptor=self.read(config['descriptor'])
  expected=dict(version='eiffel-native-search-admission-v191',source_task_id=SOURCE,
   contract=config['contract'],native_review=config['review'],implementation=config['implementation'])
  if self.descriptor!=expected or not self.review['passed']or not self.review['factory_closed']:
   raise ValueError('Qualified exact native search proof required')
  for ref in config['implementation']:self.read(ref,parse=False)
  producer=self.read(config['producer_plan'])
  if producer['capsule']!=config['producer_capsule']:raise ValueError('Original producer runtime differs')
  oldcap=self.read(config['producer_capsule']);newcap=self.read(config['current_capsule'])
  # Search semantics and capture helpers retain exact qualified bytes.
  for name in config['unchanged_native_helpers']:
   if oldcap['members'][name]!=newcap['members'][name]:
    raise ValueError('Native helper changed and needs a new code review: '+name)
   self.read(dict(path=str(self.project/name),sha256=newcap['members'][name]['sha256']),parse=False)
  raw,index=unpack(config['archive_index']['path'],config['archive']['path'],work)
  self.read(config['archive'],parse=False);self.read(config['archive_index'])
  self.baseline=load(Path(work)/'eiffel/full-native-baseline.json')['fingerprint']
  settings=load_settings(Path(config['root'])/'configs/alex.yaml')
  settings.actor.temperature=0;settings.actor.enable_thinking=False
  settings.actor.max_input_tokens=16384;settings.actor.max_new_tokens=512
  backend=TransformersChatBackend(settings.actor,str(Path(config['root'])/'models/Qwen2.5-7B-Instruct'))
  backend._tokenizer=AutoTokenizer.from_pretrained(backend.model_name,local_files_only=True,trust_remote_code=True)
  backend._tokenizer.truncation_side='left'
  count=lambda messages:len(backend._tokenizer(backend._render(messages))['input_ids'])
  cases=dict(noop='failure',wrong_query='failure',positive_result='success',positive_detail='success',
   background_tile_failure='success',search_transport_failure='unknown')
  self.replays=[];protocol=actor_protocol()
  try:
   for kind,wanted in cases.items():
    case=Path(work)/'eiffel'/kind;folder=case/'browser'
    observed=load(folder/'search-observations.json');terminal=load(folder/'search-terminal.json')
    original=load(case/'result.json')
    if not original['integrity']or not original['full_native_reset_verified']or not observed['closed']or observed['errors']:
     raise ValueError('Closed native capture and full reset required')
    if terminal['baseline']!=self.baseline:raise ValueError('Native search baseline differs')
    transport=observed['failed_requests']or observed['pending_search_requests']or[r for r in observed['native_request_metadata']
     if r.get('http_status')!=200 or r.get('actual_request_capture_error')]
    actual=evaluate(self.c,reference=self.reference,initial=observed['initial'],page=observed['terminal'],
     samples=observed['samples'],observation_directory=folder,site_origin=terminal['site_origin'],
     search_url=terminal['search_url'],integrity=True,search_transport_error=transport)
    if actual!=original['judgment']or actual['status']!=wanted:raise ValueError('Current native control differs')
    view=load(case/'public-inputs/view-000.json')
    if view['goal']!=self.c['goal']or view['label']!='original-public-start' or view['history']:
     raise ValueError('Original public initial input differs')
    prepared=protocol.prepare_observation(self.c['goal'],view['observation'],[],token_counter=count,skills=[])
    messages=protocol.messages(self.c['goal'],prepared,[],skills=[])
    sent,budget=fit_actor_messages(messages,count,16384)
    if messages!=view['protocol_messages']or sent!=view['messages']or budget!=view['observation_budget']:
     raise ValueError('Current ordinary initial request differs')
    if any(count(r['messages'])!=r['tokens']for r in view['token_counts']):
     raise ValueError('Actual initial tokenizer count differs')
    self.replays.append(dict(case=kind,status=wanted,first_input_tokens=count(sent)))
   if backend._model is not None:raise ValueError('Admission must not load model weights')
  finally:backend.close()
  self.require_current()
 def read(self,ref,*,parse=True):
  path=verified(ref);s=path.stat();self.identities[str(path)]=(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
  return load(path)if parse else path.read_bytes()
 def require_current(self):
  for path,old in self.identities.items():
   s=Path(path).stat()
   if (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)!=old:raise ValueError('Admitted search proof changed')
 def enabled(self,c):return c.get('domain')=='map'and c.get('validation_scope')==VERSION
 def canonical(self,c):
  self.require_current();value={k:v for k,v in c.items()if k!='admission_result'}
  if value!=self.c:raise ValueError('Exact original search source and scope required')
  return deepcopy(value)
 def require_admission(self,c,proof):
  self.canonical(c)
  if proof!=self.descriptor:raise ValueError('Exact native search descriptor required')
  return dict(passed=True,version=self.descriptor['version'],source_task_id=SOURCE,
   native_control_replays=6,ordinary_initial_requests_replayed=6,baseline=self.baseline)
 def require_original_binding(self,c,original,inventory):
  return require_source_binding(self.canonical(c),original,inventory,domain='map')
 def NativeReadHooks(self,c,proof,directory):
  self.require_admission(c,proof)
  hooks=SearchHooks(self.canonical(c),directory,reference=self.reference)
  prepare=hooks.prepare
  def bound_prepare(site,user):
   prepare(site,user)
   if hooks.baseline!=self.baseline:raise ValueError('Original native search baseline differs')
  hooks.prepare=bound_prepare
  return hooks
 def public_goal(self,c):return self.canonical(c)['goal']
 def fields(self,c):self.canonical(c);return []
 def feedback(self,judgment):
  if judgment.get('version')!=VERSION:raise ValueError('Exact search feedback version required')
  return dict(status=judgment['status'],reward=judgment['reward'],
   checks=[dict(condition=k,passed=v)for k,v in judgment['checks'].items()if type(v)is bool],
   private_reference_values_provided=False,action_sequence_provided=False)
