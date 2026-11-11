"""Current edit catalog preserves the qualified adapter and raw Actor evidence."""
from copy import deepcopy
from pathlib import Path
import hashlib,json
from lab_generate_skill.provider_review_catalog import identity
from lab_generate_skill.map_edit_v190.adapter import Adapter

class EditCatalog:
 def __init__(self,config,*,project):
  self.config=deepcopy(config);self.project=Path(project);self.files={}
  self.closed=False;self.sources={};self.descriptors={}
  self.config_digest=self.digest(config)
  if config.get('version')!='reviewed-native-edit-catalog-v191':
   raise ValueError('Exact native edit catalog required')
  for name,digest in config['runtime_files'].items():
   if Path(name).is_absolute()or '..'in Path(name).parts:raise ValueError('Contained runtime file required')
   self.read(dict(path=str(self.project/name),sha256=digest),parse=False)
  review=self.read(config['actor_review']);closure=self.read(config['closure_review'])
  if not review['passed']or not closure['passed']or not closure['source_result_accepted']:
   raise ValueError('Independently reviewed actual first edit Actor required')
  if closure['prior_actor_review']!=config['actor_review']or closure['judgment']!=review['judgment']:
   raise ValueError('Exact original Actor and closure binding required')
  if review['actual_actor_attempts']!=1 or review['judgment']['status']not in('success','failure'):
   raise ValueError('One valid actual edit Actor required')
  self.adapter=Adapter(self.read(config['qualified_entry_config']),project=self.project)
  c=self.adapter.c;sid=c['source_task_id']
  if config['source_ids']!=[sid]or review['source_task_id']!=sid or review['task_id']!=c['task_id']:
   raise ValueError('Qualified edit task identity differs')
  for ref in (review['plan'],review['raw_archive'],review['ordinary_archive']):
   self.read(ref,parse=False)
  self.sources[sid]=dict(candidate=deepcopy(c),admission=self.adapter.require_admission(c,self.adapter.descriptor))
  self.descriptors[sid]=deepcopy(self.adapter.descriptor)
  self.require_current()
 @staticmethod
 def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 def read(self,ref,*,parse=True):
  p=Path(ref['path']);before=identity(p);raw=p.read_bytes()
  if not p.is_absolute()or p.is_symlink()or identity(p)!=before or hashlib.sha256(raw).hexdigest()!=ref['sha256']:
   raise ValueError('Native edit evidence changed')
  self.files[p]=before
  return json.loads(raw)if parse else raw
 def require_current(self):
  if self.closed or self.digest(self.config)!=self.config_digest or any(identity(p)!=v for p,v in self.files.items()):
   raise ValueError('Native edit catalog changed or closed')
  self.adapter.require_current()
 def resolve(self,sid,descriptor):
  self.require_current()
  if sid not in self.sources or descriptor is not None and descriptor!=self.descriptors[sid]:
   raise ValueError('Exact native edit descriptor required')
  return dict(**deepcopy(self.sources[sid]),descriptor=deepcopy(self.descriptors[sid]),adapter=self.adapter)
 def close(self):self.closed=True
