"""Source-bound admission from actual category controls and ordinary entry evidence."""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit
import hashlib,json,tarfile
VERSION='admin-category-capability-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def identity(p):
 s=Path(p).stat();return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns

def verify_evidence(project,preparation):
 from . import admin_category_operations as op
 from .admin_category_rules import identity as objects,edge,position_judgment,query_judgment
 from .admin_pilot import bind,evaluate
 identities={};project=Path(project)
 def pinned(ref,decode=True):
  p=Path(ref['path']);stat=identity(p);raw=p.read_bytes()
  if hashlib.sha256(raw).hexdigest()!=ref['sha256']or identity(p)!=stat:raise ValueError('Category evidence changed')
  identities[str(p)]=stat;return json.loads(raw)if decode else raw
 def archive(ref, *, retained_query_only=False):
  raw=pinned(ref['archive'],False);idx=pinned(ref['index']);data={}
  if idx['archive_sha256']!=ref['archive']['sha256']or not idx.get('writer_termination_confirmed')or idx.get('worker_returncode')not in ((0,2)if retained_query_only else(0,)):raise ValueError('Complete category archive required')
  with tarfile.open(ref['archive']['path'])as tf:
   for m in tf:
    if not m.isfile()or m.name in data or m.name not in idx['members']:raise ValueError('Invalid category member')
    b=tf.extractfile(m).read()
    if dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())!=idx['members'][m.name]:raise ValueError('Category member changed')
    data[m.name]=b
  if set(data)!=set(idx['members']):raise ValueError('Incomplete category member coverage')
  return {k:json.loads(v)for k,v in data.items()if k.endswith('.json')}
 def check(j,want):
  if j.get('status')!=want or j.get('reward')!=(None if want=='unknown'else float(want=='success')):raise ValueError('Category control rejudgment differs')
 def reset(data,prefix,baseline,snapshot):
  r=data[prefix+'reset.json']
  if data[prefix+'restored-state.json']!=baseline or not r.get('state_equal')or not r.get('artifacts_restored')or r['state_hash']!=snapshot['state_hash']or r['sha256']!=snapshot['sha256']:raise ValueError('Full category reset differs')
 prep=pinned(preparation)
 for rel,ref in prep['changes'].items():
  if pinned(ref,False)!=(project/rel).read_bytes():
   from .admin_category_scope_compat import require_change
   identities.update(require_change(project,rel,ref))
 ordinary=pinned(prep['ordinary_review']);position=pinned(prep['position_review']);query=pinned(prep['query_review']);original=pinned(prep['source_review']);baseline=pinned(ordinary['baseline'])
 if not all(r.get('passed')is True for r in (ordinary,position,query,original)):raise ValueError('Category native review required')
 executed=pinned(ordinary['candidate_plan'])
 for overlay in executed['execution_overlays']:
  if pinned(overlay['candidate'],False)!=(project/overlay['member']).read_bytes():
   from .admin_category_scope_compat import require_change
   identities.update(require_change(project,overlay['member'],overlay['candidate']))
 if not original['train_only']or original['heldout_source_goal_trace_overlap']:raise ValueError('Training-only category sources required')
 source_defs={r['source_task_id']:r for r in original['sources']}
 for sid in op.SOURCES:
  c=op.definition(sid)
  if source_defs[sid]['original_goal']!=c['original_goal']or source_defs[sid]['original_start']!=c['start_path']:raise ValueError('Category original goal/start differs')
  loc=source_defs[sid]['source_start_provenance']['source_line']
  # The bounded original source line is retained independently of model outcomes.
  source_path=Path(loc['source_file']);source_stat=identity(source_path)
  with source_path.open('rb')as f:f.seek(loc['byte_offset']);raw=f.read(loc['byte_length'])
  if identity(source_path)!=source_stat:raise ValueError('Original category source changed while reading')
  identities[str(source_path)]=source_stat
  if hashlib.sha256(raw).hexdigest()!=loc['line_sha256']:raise ValueError('Original category source line changed')
  src=json.loads(raw)
  if src['task_id']!=sid or src['task_instruction']!=c['original_goal']:raise ValueError('Original category source identity differs')
 counts={sid:0 for sid in op.SOURCES};psid,qsid=op.SOURCES
 for record in query['source_results']:
  data=archive(record,retained_query_only=True);before=data['baseline-state.json']
  source=next(r for r in data['result.json']['source_results']if r['source_task_id']==qsid)
  if not source.get('passed')or not source.get('full_reset_verified')or data['result.json']['execution_status']!='completed':raise ValueError('Retained query source did not complete')
  if before!=baseline:raise ValueError('Retained query baseline differs')
  for name,want in [('initial','failure'),('unsent','failure'),('wrong-sku','failure'),('positive','success'),('wrong-category','failure')]:
   prefix=qsid+'/'+name
   if data[prefix+'-state.json']!=baseline:raise ValueError('Native category search changed protected state')
   j=query_judgment(baseline,data[prefix+'-view.json'],data[prefix+'-receipts.json']);check(j,want)
   if j!=data[prefix+'-judgment.json']:raise ValueError('Query control record differs')
   counts[qsid]+=1
  reset(data,qsid+'/',baseline,data['snapshot.json'])
 if counts[qsid]!=10:raise ValueError('Two native query control cycles required')
 for record in position['workers']:
  data=archive(record)
  if data['baseline-state.json']!=baseline:raise ValueError('Retained position baseline differs')
  cat,products=objects(baseline)
  for name,sku,value,want in [('initial','WSH12',0,'failure'),('unsaved','WSH12',0,'failure'),('wrong_product','WT07',10,'failure'),('wrong_position','WSH12',11,'failure'),('positive','WSH12',10,'success')]:
   prefix=psid+'/'+name+'/';state=data[prefix+'state.json'];j=position_judgment(baseline,state);check(j,want)
   if j!=data[prefix+'judgment.json']or int(edge(state,cat,products[sku])['position'])!=value:raise ValueError('Actual saved category position differs')
   reset(data,prefix,baseline,data['snapshot.json']);counts[psid]+=1
  if data[psid+'/positive/reloaded-state.json']!=data[psid+'/positive/state.json']:raise ValueError('Saved position reload differs')
  check(position_judgment(baseline,data[psid+'/positive/reloaded-state.json']),'success');counts[psid]+=1
  reset(data,psid+'/',baseline,data['snapshot.json'])
 if counts[psid]!=12:raise ValueError('Two native position control cycles required')
 results={}
 for record in ordinary['records']:
  sid=record['source_task_id'];data=archive(record);c=op.definition(sid)
  if sid not in op.SOURCES or sid in results or data['state-before.json']!=baseline:raise ValueError('Ordinary category source coverage differs')
  b=bind(op.source_row(c),baseline);local=data['binding.json']
  if {k:v for k,v in local.items()if k!='site_netloc'}!=b:raise ValueError('Ordinary category binding differs')
  first=data['initial-page.json']
  if urlsplit(first['url']).path!='/admin'+c['start_path']or data['browser/step-000.json']['action']is not None:raise ValueError('Original category start not preserved')
  for name,state,want in [('initial',baseline,'failure'),('positive',data['positive-state.json'],'success')]:
   j=evaluate(local,baseline,state,data[name+'-page.json'],'');check(j,want)
   if j!=data[name+'-judgment.json']:raise ValueError('Ordinary category terminal differs')
  if sid==qsid:
   if data['positive-state.json']!=baseline:raise ValueError('Ordinary query mutation')
   check(evaluate(local,baseline,baseline,data['wrong-page.json'],''),'failure')
  reset(data,'',baseline,data['snapshot.json']);init=data['site-logs/category-initialization.json']
  if init['source_task_id']!=sid or init['fixture_source_id']!=c['fixture_source_id']or init['receipt'].get('passed')is not True or init['receipt'].get('task_operation_precompleted')is not False:raise ValueError('Source-bound native fixture required')
  check(evaluate(local,baseline,baseline,None,''),'unknown');check(evaluate(local,baseline,baseline,first,'','injected'),'unknown')
  results[sid]=dict(task_id=sid,passed=True,binding=b,source_row=op.source_row(c),state=baseline,native_control_replays=counts[sid],ordinary_entry_replayed=True,full_reset_verified=True,training_admission=False)
 if set(results)!=set(op.SOURCES):raise ValueError('Both ordinary category sources required')
 return results,identities

@lru_cache(maxsize=2)
def _review(project,path,digest,runtime_hash):
 if sha(path)!=digest:raise ValueError('Category review changed')
 report=json.loads(Path(path).read_text())
 if report.get('version')!=VERSION or report.get('passed')is not True:raise ValueError('Category capability review required')
 results,identities=verify_evidence(project,report['preparation']);identities[path]=identity(path)
 if report['records']!={sid:{k:v for k,v in r.items()if k!='state'}for sid,r in results.items()}:raise ValueError('Category review coverage differs')
 return results,identities

def load_category_admission(base,source_id,directory):
 base,directory=Path(base),Path(directory);project=(base/'code').resolve();runtime_file=project/'configs/site-runtime-current.json';runtime=json.loads(runtime_file.read_text());runtime_hash=sha(runtime_file);cert=json.loads((directory/'category-operation-capability.json').read_text())
 if cert.get('version')!=VERSION or cert.get('source_task_id')!=source_id or cert.get('runtime_pointer_sha256')!=runtime_hash or cert.get('review')!=runtime.get('validation',{}).get('category_operation_review'):raise ValueError('Exact current category admission binding required')
 for rel,digest in runtime['actor_submission']['files_sha256'].items():
  if sha(project/rel)!=digest:raise ValueError('Frozen category runtime member changed')
 results,identities=_review(str(project),cert['review']['path'],cert['review']['sha256'],runtime_hash)
 if source_id not in results or any(identity(p)!=stat for p,stat in identities.items()):raise ValueError('Retained category evidence changed')
 result=deepcopy(results[source_id]);rows=[json.loads(l)for l in(base/'tasks.jsonl').read_text().splitlines()]
 if [r for r in rows if r['source_task_id']==source_id]!=[{**result['source_row'],'admission_path':str(directory/'result.json')}]:raise ValueError('Submitted category source differs')
 return result
