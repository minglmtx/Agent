"""Narrow listing dependency compatibility; native operation evidence stays intact."""
from pathlib import Path
import hashlib,json
from .admin_category_scope_compat import identity,read

FAMILIES={
 'native_mutation': ('admin_native_mutation_admission',frozenset(('0f2454466bc17d1e2cc2','a56c2d7739536c91fdd3','acd4566552fb8364f8ef','c0b840810cad9823b1e6'))),
 'reviewed_operation': ('admin_reviewed_operation_admission',frozenset(('7dfd7947cbf21b1561b6','c8de5316f4877a385aa2'))),
}
PAIRS={
 'native_mutation': (
  "        if pinned(ref, False) != (project/name).read_bytes():\n            raise ValueError('Reviewed mutation implementation changed: ' + name)",
  "        if pinned(ref, False) != (project/name).read_bytes():\n            from .admin_operation_scope_compat import require_change\n            identities.update(require_change(project, 'native_mutation', name, ref))"),
 'reviewed_operation': (
  "  if pinned(ref,False)!=(project/rel).read_bytes():raise ValueError('Reviewed operation code differs: '+rel)",
  "  if pinned(ref,False)!=(project/rel).read_bytes():\n   from .admin_operation_scope_compat import require_change\n   identities.update(require_change(project,'reviewed_operation',rel,ref))"),
}

def previous_source(text,family):
 old,new=PAIRS[family]
 if text.count(new)!=1:raise ValueError('Exact operation dependency check required')
 return text.replace(new,old)

def require_change(project,family,name,original):
 if family not in FAMILIES:raise ValueError('Unknown operation source family')
 module,sources=FAMILIES[family];reader='src/lab_generate_skill/'+module+'.py'
 names={'src/lab_generate_skill/admin_pilot.py',reader}
 project=Path(project).resolve();runtime=json.loads((project/'configs/site-runtime-current.json').read_text())
 identities={};update=read(runtime.get('validation',{}).get(family+'_listing_scope_review'),identities)
 if (update.get('version')!='operation-unrelated-listing-scope-v190' or update.get('family')!=family
     or update.get('passed')is not True or set(update.get('source_ids',[]))!=sources
     or set(update.get('changes',{}))!=names or name not in names):
  raise ValueError('Exact operation source dependency scope required')
 if original['sha256']!=update['changes'][name]['old_sha256']:
  raise ValueError('Historical operation dependency differs')
 projection=read(update['old_scope_projection'],identities);specs=read(update['listing_spec_isolation'],identities)
 if (projection.get('passed')is not True or specs.get('passed')is not True
     or specs.get('unchanged_existing_admin_specs')!=451 or specs.get('intentionally_revised_admin_bindings')!=5):
  raise ValueError('Unrelated listing scope isolation missing')
 for relative,pair in update['changes'].items():
  path=project/relative;before=identity(path);raw=path.read_bytes()
  if (hashlib.sha256(raw).hexdigest()!=pair['current_sha256'] or identity(path)!=before
      or runtime['actor_submission']['files_sha256'].get(relative)!=pair['current_sha256']):
   raise ValueError('Current operation dependency differs')
  identities[str(path)]=before
  matches=[r for r in projection['rows']if r['path']==relative and r['old_sha256']==pair['old_sha256']
      and r['current_sha256']==pair['current_sha256'] and r.get('remaining_ast_identical')is True]
  if len(matches)!=1:raise ValueError('Applicable operation projection missing')
  if relative==reader and hashlib.sha256(previous_source(raw.decode(),family).encode()).hexdigest()!=pair['old_sha256']:
   raise ValueError('Native operation proof logic changed beyond the dependency check')
 # The callers still verify original source rows, native archives, all controls,
 # full resets and actual current business verdicts, with cache identity tracking.
 return identities
