"""Source-bound retained controls for the two reviewed Admin operations."""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit
import hashlib,json,tarfile

VERSION='admin-reviewed-operation-capability-v1'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def identity(p):
 s=Path(p).stat();return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns

def verify_evidence(project,preparation):
 from . import admin_reviewed_operations as op
 from .admin_pilot import bind,evaluate,canonical_hash
 project=Path(project);identities={}
 def pinned(ref,decode=True):
  p=Path(ref['path']);initial=identity(p);raw=p.read_bytes()
  if hashlib.sha256(raw).hexdigest()!=ref['sha256']or identity(p)!=initial:raise ValueError('Reviewed operation evidence changed: '+str(p))
  identities[str(p)]=initial
  return json.loads(raw)if decode else raw
 prep=pinned(preparation)
 for rel,ref in prep['changes'].items():
  if pinned(ref,False)!=(project/rel).read_bytes():
   from .admin_operation_scope_compat import require_change
   identities.update(require_change(project,'reviewed_operation',rel,ref))
 for record in prep['pure_core_extraction']:
  source=pinned(record['original'],False).decode();core=pinned(record['candidate'],False)
  if core!=(source[:source.index('\ndef run(')]+'\n').encode():raise ValueError('Native evaluator core differs')
 reviews=[pinned(r)for r in prep['source_reviews']]
 date=next(r for r in reviews if 'new_archive'in r);design=next(r for r in reviews if 'cycles'in r)
 def archive(ref):
  pinned(ref['archive'],False);index=pinned(ref['index']);members=index['members'];data={}
  if index['archive_sha256']!=ref['archive']['sha256']:raise ValueError('Archive index differs')
  with tarfile.open(ref['archive']['path'])as handle:
   for member in handle:
    if not member.isfile()or member.name not in members or member.name in data:raise ValueError('Invalid retained member')
    raw=handle.extractfile(member).read();record=members[member.name]
    if len(raw)!=record['bytes']or hashlib.sha256(raw).hexdigest()!=record['sha256']:raise ValueError('Retained member changed')
    data[member.name]=raw
  if set(data)!=set(members):raise ValueError('Incomplete retained archive')
  return data
 def check(score,expected):
  if score['status']!=expected or score['reward']!=(None if expected=='unknown'else float(expected=='success')):raise ValueError('Retained ordinary operation score differs')
 results={};data=archive(design['archive']);states=[];paths=[];count=0
 c=op.definition(op.DESIGN)
 for i in (0,1):
  prefix=f'worker/evidence/cycle-{i}/';read=lambda n:json.loads(data[prefix+n])
  before=read('cold-state.json');states.append(before);cy=read('result.json');paths.append(cy['fresh_site_path'])
  if before!=read('restored-state.json')or before!=read('controls/before-state.json')or not all(cy.get(k)is True for k in ('passed','native_state_restored','private_factory_terminated','private_state_removed'))or cy['database_reset']['state_equal']is not True:raise ValueError('Full product factory reset evidence required')
  binding=bind(op.source_row(c),before);initial=read('browser/initial-page.json')
  if urlsplit(initial['url']).path!='/admin'+c['start_path']:raise ValueError('Original product start differs')
  page=read('controls/saved-page.json');local=dict(binding,site_netloc=urlsplit(page['url']).netloc)
  controls=read('controls/controls.json')
  expected={'initial_noop':'failure','unsaved_creation':'failure','saved_wrong_layout':'failure','unsaved_layout_fix':'failure','saved_correct_layout':'success','fresh_saved_layout':'success','missing_native_eav':'unknown','synthetic_wrong_saved_layout':'failure','changed_eav_schema':'unknown'}
  if set(controls)!=set(expected):raise ValueError('Product controls incomplete')
  for name,status in expected.items():
   if controls[name]['expected']!=status:raise ValueError('Product control expectation changed')
   check(evaluate(local,before,read('controls/'+name+'-state.json'),page,''),status);count+=1
  if read('controls/fresh-state.json')!=read('controls/saved_correct_layout-state.json'):raise ValueError('Fresh saved design differs')
  actions=read('controls/native-actions.json')
  if not all(a.get('completed')for a in actions)or sum(a['kind']=='click'and a['selector']=='#save-button'for a in actions)!=2:raise ValueError('Actual save evidence required')
 if states[0]!=states[1]or paths[0]==paths[1]:raise ValueError('Independent equal product factories required')
 results[op.DESIGN]=dict(task_id=op.DESIGN,passed=True,binding=binding,state=states[0],source_row=op.source_row(c),native_control_replays=count,full_reset_cycles=2,independent_cold_starts_claimed=True,training_admission=False)
 old=pinned(date['old_cycle_rejudgment']);oldref=prep['old_date_archive'];
 if oldref['archive']!=old['archive']:raise ValueError('Original date archive differs')
 states=[];factories=[];count=0;c=op.definition(op.DATE)
 for i,ref in enumerate((oldref,date['new_archive'])):
  data=archive(ref);prefix=f'cycles/{op.DATE}/{i}/';read=lambda n:json.loads(data[prefix+n]);cy=read('result.json');ev=read('controls/full-date-evidence.json');before=ev['before'];states.append(before)
  factories.append({n.split('/')[1]for n in data if n.startswith('site-logs/stage1-site-')})
  if cy.get('full_reset_verified')is not True or cy['reset'].get('state_equal')is not True or cy['reset'].get('artifacts_restored')is not True or cy['reset']['state_hash']!=canonical_hash(before)or before!=read('restored-state.json')or before!=json.loads(data['baseline-state.json']):raise ValueError('Full date reset evidence required')
  binding=bind(op.source_row(c),before);initial=read('browser/initial-page.json')
  if urlsplit(initial['url']).path!='/admin'+c['start_path']or read('browser/step-000.json')['action']is not None:raise ValueError('Original date start differs')
  page=read('controls/operation/applied-page.json');local=dict(binding,site_netloc=urlsplit(page['url']).netloc);page['ui_contract']['grid_operation']=ev['grid'];page[op.PAGE_KEY]=dict(provider_items=ev['provider_items'],visible_rows=ev['visible_rows'])
  check(evaluate(local,before,ev['after'],page,''),'success');count+=1
  # Provider/request component controls retain their own captured inputs.
  # They do not contain matching full-page item captures for the full judge.
  controls=read('controls/operation/control-results.json')
  expected={'initial_no_filter':'failure','typed_without_apply':'failure','native_date_filter_applied':'success','wrong_date':'failure','response_not_applied':'failure','missing_request':'failure','missing_probe':'unknown'}
  if set(controls)!=set(expected):raise ValueError('Date component controls incomplete')
  for name,status in expected.items():
   if controls[name]['expected']!=status:raise ValueError('Date control expectation changed')
   from .admin_calendar_grid_checks import checks as grid_checks
   try:actual='success'if all(grid_checks(c['required_grid_operation'],read('controls/operation/'+name+'-grid.json')).values())else'failure'
   except (ValueError,KeyError,TypeError):actual='unknown'
   if actual!=status:raise ValueError('Retained date component score differs: '+name)
   count+=1
 if states[0]!=states[1]or not all(factories)or factories[0]&factories[1]:raise ValueError('Independent equal date factories required')
 results[op.DATE]=dict(ordinary_full_positive_replays=2,component_control_replays=14,task_id=op.DATE,passed=True,binding=binding,state=states[0],source_row=op.source_row(c),native_control_replays=count,full_reset_cycles=2,independent_cold_starts_claimed=True,training_admission=False)
 return results,identities

@lru_cache(maxsize=2)
def _review(project,review_path,review_hash,runtime_hash):
 raw=Path(review_path).read_bytes()
 if hashlib.sha256(raw).hexdigest()!=review_hash:raise ValueError('Operation review changed')
 report=json.loads(raw)
 if report.get('version')!=VERSION or report.get('passed')is not True:raise ValueError('Reviewed operation preparation required')
 results,identities=verify_evidence(project,report['preparation']);identities[review_path]=identity(review_path)
 if report['records']!={sid:{k:v for k,v in row.items()if k!='state'}for sid,row in results.items()}:raise ValueError('Operation review coverage differs')
 return results,identities

def load_reviewed_operation_admission(base,source_id,directory):
 base,directory=Path(base),Path(directory);project=(base/'code').resolve();runtime_file=project/'configs/site-runtime-current.json';runtime=json.loads(runtime_file.read_text());runtime_hash=sha(runtime_file)
 cert=json.loads((directory/'reviewed-operation-capability.json').read_text())
 if cert.get('version')!=VERSION or cert.get('source_task_id')!=source_id or cert.get('runtime_pointer_sha256')!=runtime_hash or cert.get('review')!=runtime.get('validation',{}).get('reviewed_operation_review'):raise ValueError('Exact frozen operation admission binding required')
 for rel,digest in runtime['actor_submission']['files_sha256'].items():
  if sha(project/rel)!=digest:raise ValueError('Frozen operation runtime member changed: '+rel)
 results,identities=_review(str(project),cert['review']['path'],cert['review']['sha256'],runtime_hash)
 if source_id not in results or any(identity(p)!=value for p,value in identities.items()):raise ValueError('Operation source or retained proof changed')
 result=deepcopy(results[source_id]);rows=[json.loads(line)for line in (base/'tasks.jsonl').read_text().splitlines()]
 if [r for r in rows if r['source_task_id']==source_id]!=[{**result['source_row'],'admission_path':str(directory/'result.json')}]:raise ValueError('Submitted operation source differs')
 return result
