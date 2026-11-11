"""Preserve the CSV producer while admitting one proved unrelated listing delta."""
from copy import deepcopy
from pathlib import Path
import hashlib,json

SOURCE='986fe7a818c13d647950'
DEPENDENCY='src/lab_generate_skill/admin_pilot.py'

def read_pin(reference):
    if not isinstance(reference,dict) or set(reference)!={'path','sha256'}:
        raise ValueError('Exact listing compatibility evidence pin required')
    path=Path(reference['path'])
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError('Absolute regular listing compatibility evidence required')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=reference['sha256']:
        raise ValueError('Listing compatibility evidence changed')
    return json.loads(raw)

def catalog_class(Base,config,project,*,legacy):
    if config.get('source_task_id')!=SOURCE:
        raise ValueError('Listing dependency update applies only to the original CSV intake')
    update=read_pin(config['reviewed_native_listing_intake'])
    if (update.get('version')!='csv-unrelated-listing-dependency-v190'
            or update.get('source_task_id')!=SOURCE or update.get('passed') is not True
            or set(update.get('changes',{}))!={DEPENDENCY}):
        raise ValueError('Exactly one source-bound CSV dependency delta required')
    root=Path(project).resolve();pair=update['changes'][DEPENDENCY]
    before=Path(pair['previous_file']['path'])
    if before.is_symlink() or hashlib.sha256(before.read_bytes()).hexdigest()!=pair['old_sha256'] or pair['previous_file']['sha256']!=pair['old_sha256']:
        raise ValueError('Original CSV runtime dependency changed')
    if hashlib.sha256((root/DEPENDENCY).read_bytes()).hexdigest()!=pair['current_sha256']:
        raise ValueError('Current CSV dependency differs from reviewed code')
    projection=read_pin(update['old_scope_projection'])
    matches=[r for r in projection['rows']if r['path']==DEPENDENCY]
    if (not projection.get('passed') or len(matches)!=1 or matches[0]['old_sha256']!=pair['old_sha256']
            or matches[0]['current_sha256']!=pair['current_sha256']
            or matches[0].get('remaining_ast_identical') is not True):
        raise ValueError('Unchanged non-listing execution has not been proved')
    original=deepcopy(config);original.pop('reviewed_native_listing_intake')
    Parent=legacy(Base,original,root)
    class CurrentListingDependency(Parent):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            self.read(config['reviewed_native_listing_intake'])
            self.read(update['old_scope_projection'])
            self.read(pair['previous_file'],raw=True)

        def read(self,reference,*,raw=False):
            path=Path(reference['path'])
            if raw and path==root/DEPENDENCY:
                if reference['sha256']!=pair['old_sha256']:
                    raise ValueError('Original CSV producer dependency differs')
                reference=dict(reference,sha256=pair['current_sha256'])
            return super().read(reference,raw=raw)
    return CurrentListingDependency
