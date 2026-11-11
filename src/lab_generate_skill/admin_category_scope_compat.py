"""Accept only proved listing-scope changes in unchanged category evidence."""
from pathlib import Path
import hashlib,json

NAMES=frozenset(('configs/admin-navigation-extension-v1.json',
    'configs/admin-completion-contracts-v1.json','src/lab_generate_skill/admin_pilot.py',
    'src/lab_generate_skill/admin_ui_contract.py','src/lab_generate_skill/admin_category_admission.py'))
SOURCES=frozenset(('65d44f1f647a37cce37a','b3948d69b63665617e41'))
PAIRS=(
    ("  if pinned(ref,False)!=(project/rel).read_bytes():raise ValueError('Category implementation differs: '+rel)",
     "  if pinned(ref,False)!=(project/rel).read_bytes():\n   from .admin_category_scope_compat import require_change\n   identities.update(require_change(project,rel,ref))"),
    ("  if pinned(overlay['candidate'],False)!=(project/overlay['member']).read_bytes():raise ValueError('Ordinary tested category implementation differs')",
     "  if pinned(overlay['candidate'],False)!=(project/overlay['member']).read_bytes():\n   from .admin_category_scope_compat import require_change\n   identities.update(require_change(project,overlay['member'],overlay['candidate']))"),
)

def previous_source(text):
    for old,new in PAIRS:
        if text.count(new)!=1:raise ValueError('Exact scoped category evidence checks required')
        text=text.replace(new,old)
    return text

def identity(path):
    value=Path(path).stat()
    return value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns

def read(reference,identities):
    if not isinstance(reference,dict) or set(reference)!={'path','sha256'}:
        raise ValueError('Pinned category scope compatibility required')
    path=Path(reference['path']);before=identity(path);raw=path.read_bytes()
    if not path.is_absolute() or path.is_symlink() or hashlib.sha256(raw).hexdigest()!=reference['sha256'] or identity(path)!=before:
        raise ValueError('Category scope evidence changed')
    identities[str(path)]=before
    return json.loads(raw)

def require_change(project,name,original):
    project=Path(project).resolve()
    runtime=json.loads((project/'configs/site-runtime-current.json').read_text())
    identities={}
    update=read(runtime.get('validation',{}).get('category_listing_scope_review'),identities)
    if (update.get('version')!='category-unrelated-listing-scope-v190' or update.get('passed') is not True
            or set(update.get('source_ids',[]))!=SOURCES or set(update.get('changes',{}))!=NAMES
            or name not in NAMES):
        raise ValueError('Exact unchanged category source dependency scope required')
    pair=update['changes'][name]
    if original['sha256']!=pair['old_sha256']:
        raise ValueError('Historical category producer dependency differs')
    raw=(project/name).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=pair['current_sha256'] or runtime['actor_submission']['files_sha256'].get(name)!=pair['current_sha256']:
        raise ValueError('Current category dependency differs from reviewed source')
    projection=read(update['old_scope_projection'],identities);specs=read(update['listing_spec_isolation'],identities)
    if (not projection.get('passed') or not specs.get('passed')
            or specs.get('unchanged_existing_admin_specs')!=451 or specs.get('intentionally_revised_admin_bindings')!=5):
        raise ValueError('Unrelated listing scope isolation has not been established')
    if name.endswith('.py'):
        matches=[r for r in projection['rows']if r['path']==name and r['old_sha256']==pair['old_sha256']
                 and r['current_sha256']==pair['current_sha256'] and r.get('remaining_ast_identical')is True]
        if len(matches)!=1:raise ValueError('Applicable category execution projection missing')
        if name.endswith('/admin_category_admission.py'):
            if hashlib.sha256(previous_source(raw.decode()).encode()).hexdigest()!=pair['old_sha256']:
                raise ValueError('Category proof logic changed beyond the two declared dependency checks')
    else:
        qualified=pair['qualified_listing_file'];path=Path(qualified['path'])
        before=identity(path)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=qualified['sha256'] or path.read_bytes()!=raw or identity(path)!=before:
            raise ValueError('Configuration differs from the tested five-listing candidate')
        identities[str(path)]=before
    # Original source lines, native states, reset archives, controls and current
    # business judgments still pass through the unchanged category verifier.
    return identities
