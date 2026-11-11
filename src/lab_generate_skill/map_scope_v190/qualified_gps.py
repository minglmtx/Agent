"""Ordinary terminal-only GPS adapter with replayed immutable native admission."""
from pathlib import Path,PurePosixPath
from copy import deepcopy
from types import SimpleNamespace
from urllib.parse import urlsplit
import hashlib,json,tarfile
from gps_hooks import GPSDocumentHooks
from gps_terminal import evaluate_gps,GPS_VERSION,GPS_SOURCE
from lab_generate_skill.map_provider_resources import checked_archive,member,validate_tile
from lab_generate_skill.source_revision_binding import require_source_binding,binding

def read(ref):
 p=Path(ref['path']);assert p.is_absolute()and not p.is_symlink();raw=p.read_bytes()
 assert hashlib.sha256(raw).hexdigest()==ref['sha256'],str(p)
 return json.loads(raw)

class Adapter:
 FEEDBACK_VERSIONS=(GPS_VERSION,)
 AUTHORIZED_TARGET_WRITES=False
 def __init__(self,plan):
  self.plan=plan;self.c=read(plan['contracts'])['tasks'][0];binding(self.c)
  self.review=read(plan['native_review']);self.descriptor=read(plan['descriptor'])
  assert self.review['passed']and self.review['source_task_id']==GPS_SOURCE
  assert self.review['terminal_judgments_replayed']==self.review['actual_first_native_inputs_reconstructed']==5
  assert self.review['runtime_module_hashes_verified']and self.review['all_archive_members_verified']
  assert self.descriptor==dict(version='native-gps-document-ordinary-admission-v190',source_task_id=GPS_SOURCE,task_id=self.c['task_id'],native_review=plan['native_review'])
  resources=read(plan['resources']);upstream={s['sha256']:checked_archive(s)for s in resources['sources']};bodies={}
  for key,row in resources['providers']['gps']['files'].items():
   raw=upstream[row['archive_sha256']];validate_tile('gps',key,row,raw);bodies['/tiles/gps/'+key]=member(raw,row)
  for case in plan['case_archives']:
   manifest=read(case['manifest']);path=Path(case['archive']['path']);assert hashlib.sha256(path.read_bytes()).hexdigest()==case['archive']['sha256']==manifest['archive_sha256']
   files={}
   with tarfile.open(path)as t:
    for m in t:
     p=PurePosixPath(m.name);assert m.isfile()and not p.is_absolute()and '..'not in p.parts and m.name not in files
     raw=t.extractfile(m).read();assert manifest['members'][m.name]==dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest());files[m.name]=raw
   assert set(files)==set(manifest['members'])
   term=json.loads(files['browser/gps-terminal.json']);result=json.loads(files['result.json'])
   assert result['passed']and result['full_native_reset_verified']and result['error']is None
   assert term['baseline']==self.review['baseline']and term['environment_binding']==self.review['environment_binding']
   u=urlsplit(term['initial_document']['url']);origin=u.scheme+'://'+u.netloc
   server_url=(term['native_terminal']or{}).get('template','').split('/tiles/gps/')[0]
   verdict=evaluate_gps(self.c,initial_document=term['initial_document'],terminal=term['native_terminal'],page=term['terminal'],site_origin=origin,server=SimpleNamespace(url=server_url,bodies=bodies),response_hashes=term['response_sha256'],response_errors=term['response_errors'],integrity=term['integrity'],capture_error=term['capture_error'])
   assert verdict==term['judgment']==result['judgment']and verdict['status']==result['expected']
  assert len(plan['case_archives'])==5
 def enabled(self,c):return c.get('domain')=='map'and c.get('candidate_completion',{}).get('family')=='gps_overlay_enabled'
 def canonical(self,c):
  value={k:v for k,v in c.items()if k!='admission_result'}
  if value!=self.c:raise ValueError('Exact reviewed GPS goal/source/start required')
  return deepcopy(value)
 def require_admission(self,c,proof):
  self.canonical(c)
  if proof!=self.descriptor:raise ValueError('Exact immutable native proof descriptor required')
  if read(self.plan['native_review'])!=self.review:raise ValueError('Admission changed')
  return dict(passed=True,version=self.descriptor['version'],baseline=self.review['baseline'],environment_binding=self.review['environment_binding'])
 def require_original_binding(self,c,original,inventory):return require_source_binding(self.canonical(c),original,inventory,domain='map')
 def NativeReadHooks(self,c,proof,directory):
  self.require_admission(c,proof)
  return GPSDocumentHooks(self.canonical(c),directory,environment_binding=self.review['environment_binding'],baseline=self.review['baseline'])
 def public_goal(self,c):return self.canonical(c)['goal']
 def fields(self,c):self.canonical(c);return []
 def feedback(self,judgment):
  if judgment.get('version')!=GPS_VERSION:raise ValueError('Exact GPS final-only feedback required')
  return dict(status=judgment['status'],reward=judgment['reward'],checks=[dict(condition=k,passed=v)for k,v in judgment['checks'].items()if type(v)is bool],private_reference_values_provided=False,action_sequence_provided=False)
