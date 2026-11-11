"""Exact source admission with retained native controls and complete cold reset."""
from pathlib import Path,PurePosixPath
from copy import deepcopy
import hashlib,json,tarfile
from edit_judge import evaluate
from lab_generate_skill.source_revision_binding import binding,require_source_binding
from .profile import validate_profile
from .hooks import NativeEditHooks,VERSION

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def identity(path):
 s=Path(path).stat();return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns

class Adapter:
 FEEDBACK_VERSIONS=(VERSION,)
 AUTHORIZED_TARGET_WRITES=True
 def __init__(self,config,*,project):
  self.config=deepcopy(config);self.config_digest=digest(config);self.project=Path(project).resolve();self.identities={}
  self.c=self.read(config['contract']);binding(self.c)
  self.profile=validate_profile(self.read(config['profile']))
  self.review=self.read(config['native_review']);self.descriptor=self.read(config['descriptor'])
  self.inventory=self.read(config['source_inventory_row'])
  require_source_binding(self.c,self.c,self.inventory,domain='map')
  if not self.review['passed']or not self.review['all_raw_members_verified']or not self.review['independent_cold_reset_full_state_equal']:
   raise ValueError('Full native controls and independent cold reset required')
  if self.review['source_task_id']!=self.c['source_task_id']or self.review['task_id']!=self.c['task_id']:
   raise ValueError('Qualified native source identity differs')
  expected=dict(version='native-node-edit-ordinary-admission-v190',source_task_id=self.c['source_task_id'],task_id=self.c['task_id'],
   native_review=config['native_review'],contract=config['contract'],profile=config['profile'],implementation_sha256=config['implementation_sha256'])
  if self.descriptor!=expected:raise ValueError('Exact source-specific ordinary admission descriptor required')
  for relative,value in config['implementation_sha256'].items():
   if Path(relative).is_absolute()or '..'in Path(relative).parts:raise ValueError('Contained frozen implementation required')
   self.read(dict(path=str(self.project/relative),sha256=value),parse=False)
  for name,original in config['qualified_files'].items():
   if self.read(original,parse=False)!=(self.project/'scripts'/name).read_bytes():
    raise ValueError('Qualified native editor/capture/protection/judge changed')
  plan=self.read(self.review['plan']);original=self.read(plan['contract'])
  for key in ('task_id','source_task_id','domain','split','original_goal','goal','parameters','completion_boundary'):
   if self.c[key]!=original[key]:raise ValueError('Public native edit scope changed: '+key)
  metadata=self.read(config['source_metadata_review'])
  if (metadata.get('passed')is not True or metadata['complete_source_trace_ids']!=self.c['source_trace_ids']
      or metadata['original_recorded_start_path']!=self.c['start_path']
      or metadata['previous_numeric_spelling']!=original['start_path']
      or metadata['previous_incomplete_trace_ids']!=original['source_trace_ids']):
   raise ValueError('Exact complete original source metadata correction required')
  from urllib.parse import urlsplit,parse_qs
  from decimal import Decimal
  def shape(value):
   u=urlsplit(value);q=parse_qs(u.query);route=q.pop('route')
   if len(route)!=1:raise ValueError('One original route start required')
   return u.path,q,[[Decimal(x)for x in pair.split(',')]for pair in route[0].split(';')],u.fragment
  if shape(original['start_path'])!=shape(self.c['start_path']):raise ValueError('Qualified original geographic start changed')
  data=self.archive(self.review['raw_archive'],config['native_archive_index'])
  read=lambda name:json.loads(data[name]);self.baseline=read('baseline.json')
  if self.baseline!=read('cold-reset.json'):raise ValueError('Full native cold reset differs')
  result=read('result.json')
  if not all(result.get(k)is True for k in ('passed','dirty_reuse_refused','first_factory_closed','second_factory_closed','cold_reset_restored_original_object_and_guard')):
   raise ValueError('Closed native factories and dirty-reuse refusal required')
  expected={'noop':'failure','unsaved':'failure','wrong_saved_value':'failure','saved_without_reopen':'failure',
   'readback_transport_failure':'unknown','saved_and_reopened':'success','navigate_after_readback':'success'}
  if {r['name']:r['status']for r in self.review['native_cases']}!=expected:raise ValueError('Native boundary case coverage differs')
  for name,status in expected.items():
   if read(name+'/baseline.json')!=self.baseline:raise ValueError('Native case baseline differs')
   score=evaluate(self.c,self.baseline,read(name+'/state.json'),read(name+'/witness.json'))
   if score!=read(name+'/verdict.json')or score['status']!=status:raise ValueError('Native current verdict differs: '+name)
  self.control_replays=len(expected);self.require_current()
 def read(self,reference,*,parse=True):
  if not isinstance(reference,dict)or set(reference)!={'path','sha256'}:raise ValueError('Pinned native evidence required')
  path=Path(reference['path']);before=identity(path);raw=path.read_bytes()
  if not path.is_absolute()or path.is_symlink()or hashlib.sha256(raw).hexdigest()!=reference['sha256']or identity(path)!=before:
   raise ValueError('Native edit evidence changed: '+str(path))
  self.identities[str(path)]=before
  return json.loads(raw)if parse else raw
 def archive(self,reference,index_ref):
  self.read(reference,parse=False);index=self.read(index_ref);data={}
  if index['archive_sha256']!=reference['sha256']:raise ValueError('Native archive identity differs')
  with tarfile.open(reference['path'])as tar:
   for item in tar:
    name=PurePosixPath(item.name)
    if not item.isfile()or name.is_absolute()or '..'in name.parts or item.name in data:raise ValueError('Invalid native evidence member')
    raw=tar.extractfile(item).read()
    if index['members'].get(item.name)!=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()):raise ValueError('Native evidence member changed')
    data[item.name]=raw
  if data.keys()!=index['members'].keys():raise ValueError('Incomplete native raw archive')
  return data
 def require_current(self):
  if digest(self.config)!=self.config_digest or any(identity(p)!=old for p,old in self.identities.items()):raise ValueError('Native edit admission changed')
 def enabled(self,c):return c.get('domain')=='map'and c.get('validation_scope')==VERSION
 def canonical(self,c):
  self.require_current();value={k:v for k,v in c.items()if k!='admission_result'}
  if value!=self.c:raise ValueError('Exact declared edit source, goal, parameters and original start required')
  return deepcopy(value)
 def require_admission(self,c,proof):
  self.canonical(c)
  if proof!=self.descriptor:raise ValueError('Exact native edit admission required')
  return dict(passed=True,version=self.descriptor['version'],native_control_replays=self.control_replays,
   independent_full_cold_reset=True,source_task_id=self.c['source_task_id'],baseline=deepcopy(self.baseline))
 def require_original_binding(self,c,original,inventory):return require_source_binding(self.canonical(c),original,inventory,domain='map')
 def NativeReadHooks(self,c,proof,directory):
  self.require_admission(c,proof);return NativeEditHooks(self.canonical(c),directory,baseline=self.baseline)
 def public_goal(self,c):return self.canonical(c)['goal']
 def fields(self,c):self.canonical(c);return []
 def profile_for_contracts(self,rows):
  if len(rows)!=1:raise ValueError('Native editor requires a dedicated source manifest')
  self.canonical(rows[0]);return dict(map_saved_node_editor=deepcopy(self.profile))
 def feedback(self,judgment):
  if judgment.get('version')!=VERSION:raise ValueError('Exact native editor terminal feedback required')
  return dict(status=judgment['status'],reward=judgment['reward'],checks=[dict(condition=k,passed=v)for k,v in judgment['checks'].items()if type(v)is bool],
   private_reference_values_provided=False,action_sequence_provided=False)
