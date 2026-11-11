"""Reissue only metadata of explicitly reviewed native Admin certificates.

The immutable original archive stays intact. All existing native operation,
initial-state, reset and scoring gates still run on its unchanged evidence.
An archive, source ID or old success label cannot authorize a reissue alone.
"""
from pathlib import Path
import hashlib,json

VERSION='verified-admin-current-certificate-binding-v1'
CERTIFICATES={'native-capability.json','navigation-capability.json',
              'contract-capability.json','material-capability.json','creation-capability.json',
              'native-mutation-capability.json','reviewed-operation-capability.json','category-operation-capability.json'}

def _read_pin(reference):
    if not isinstance(reference,dict)or set(reference)!={'path','sha256'}:
        raise ValueError('Exact certificate binding pin required')
    path=Path(reference['path'])
    if not path.is_absolute()or path.is_symlink()or not path.is_file():
        raise ValueError('Regular absolute binding input required')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=reference['sha256']:
        raise ValueError('Certificate binding input changed')
    return json.loads(raw)

def reissue_reviewed_certificate(record,directory,*,project):
    reference=record.get('current_runtime_binding')
    if reference is None:
        return None  # The original strict loader still decides admission.
    directory,project=Path(directory),Path(project).resolve()
    config_file=project/'configs/site-runtime-current.json'
    raw=config_file.read_bytes();current=json.loads(raw)
    if reference!=current.get('validation',{}).get('current_admin_certificate_binding'):
        raise ValueError('Certificate authority is not the current published authority')
    authority=_read_pin(reference)
    if(authority.get('version')!=VERSION or authority.get('runtime_version')!=current['version']
       or authority.get('current_runtime_files_sha256')!=current['actor_submission']['files_sha256']):
        raise ValueError('Certificate authority belongs to another runtime')
    source=directory.name
    records=authority.get('sources',{})
    if not isinstance(records,dict)or source not in records:
        raise ValueError('Admin source has no reviewed certificate binding')
    entry=records[source]
    if entry.get('source_task_id')!=source or entry.get('archive')!={'path':record['archive'],'sha256':record['archive_sha256']}:
        raise ValueError('Admin source/archive differs from reviewed evidence')
    certificate=entry.get('certificate_file')
    if certificate not in CERTIFICATES:
        raise ValueError('Unsupported reviewed certificate protocol')
    files=[p for p in directory.glob('*-capability.json')]
    if len(files)!=1 or files[0].name!=certificate or files[0].is_symlink():
        raise ValueError('Exactly one source-bound native certificate required')
    path=files[0];old_raw=path.read_bytes();original=json.loads(old_raw)
    if(hashlib.sha256(old_raw).hexdigest()!=entry.get('original_certificate_sha256')
       or original.get('source_task_id')!=source
       or original.get('version')!=entry.get('certificate_version')):
        raise ValueError('Original reviewed certificate changed')
    review=_read_pin(authority['applicable_code_review'])
    if not review.get('passed')or not review.get('native_operation_goal_start_reset_and_evaluator_preserved'):
        raise ValueError('Applicable native code compatibility is not established')
    for relative,digest in review['unchanged_applicable_files'].items():
        local=Path(relative)
        if local.is_absolute()or '..'in local.parts:
            raise ValueError('Invalid applicable code member')
        if hashlib.sha256((project/local).read_bytes()).hexdigest()!=digest:
            raise ValueError('Applicable native code changed: '+relative)
    updates=entry.get('certificate_updates',{})
    validation_key={'material-capability.json':'guard_validation','creation-capability.json':'validation'}.get(certificate)
    allowed={'compatibility'}|({validation_key} if validation_key else set())
    if not isinstance(updates,dict)or set(updates)-allowed:
        raise ValueError('A certificate reissue cannot change native proof fields')
    if updates:
        if certificate not in {'material-capability.json','creation-capability.json'}:
            raise ValueError('This certificate cannot replace compatibility metadata')
        if 'compatibility' not in updates:
            raise ValueError('Reviewed validation requires native compatibility')
        compatibility=_read_pin(updates['compatibility'])
        if(compatibility.get('version')!=current['version']
           or compatibility.get('current_files_sha256')!=current['actor_submission']['files_sha256']
           or compatibility.get('environment_actions_reset_unchanged')is not True
           or compatibility.get('native_capsule')!=original.get('native_capsule')):
            raise ValueError('Material compatibility does not preserve its native evidence')
    if validation_key and validation_key in updates:
        prior=_read_pin(original[validation_key])
        validated=_read_pin(updates[validation_key])
        # Only the manifest's exact tested-code hashes can be reissued. Its
        # passed flag, native archive and all scientific evidence stay equal.
        if (prior.get('passed') is not True or validated.get('passed') is not True
                or {k:v for k,v in prior.items() if k!='tested_files'}
                != {k:v for k,v in validated.items() if k!='tested_files'}
                or not isinstance(prior.get('tested_files'),dict)
                or validated.get('tested_files')!={n:current['actor_submission']['files_sha256'].get(n)
                                                  for n in prior['tested_files']}
                or any(v is None for v in validated['tested_files'].values())):
            raise ValueError('Native validation evidence or tested-file scope changed')
        regression=_read_pin(review['regression'])
        if regression.get('returncode')!=0:
            raise ValueError('Current tested-code regression did not pass')
    changed={**original,**updates,'runtime_pointer_sha256':hashlib.sha256(raw).hexdigest()}
    new_raw=(json.dumps(changed,indent=2)+'\n').encode()
    temporary=path.with_name(path.name+'.rebinding');temporary.write_bytes(new_raw);temporary.replace(path)
    receipt={'version':VERSION,'source_task_id':source,'authority':reference,
             'original_archive':entry['archive'],
             'original_certificate_sha256':entry['original_certificate_sha256'],
             'current_certificate_sha256':hashlib.sha256(new_raw).hexdigest(),
             'changed_fields':sorted({'runtime_pointer_sha256',*updates}),
             'native_evidence_and_result_unchanged':True,'training_admitted':False}
    (directory/'current-certificate-binding.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt
