"""Narrow current-interface intake adapters; native proofs retain producer bytes."""
from pathlib import Path
from copy import deepcopy
import hashlib,json
SHARED={'src/lab_generate_skill/'+n+'.py'for n in ('actor_protocol','adaptive_observation','runtime_profile','public_read_memory')}

def checked(ref):
    p=Path(ref['path'])
    if not p.is_absolute()or p.is_symlink()or not p.is_file()or hashlib.sha256(p.read_bytes()).hexdigest()!=ref['sha256']:raise ValueError('Exact interface review required')
    return json.loads(p.read_text())

def review(config,project):
    x=checked(config['reviewed_shared_interface_intake'])
    if x.get('version')!='reviewed-lossless-intake-v185'or x.get('passed')is not True or set(x['changes'])!=SHARED:raise ValueError('Exact four-module interface review required')
    for n,r in x['changes'].items():
        p=Path(project)/n
        if p.is_symlink()or hashlib.sha256(p.read_bytes()).hexdigest()!=r['current_sha256']:raise ValueError('Current interface differs from review')
    evidence=checked(x['shared_regression'])
    if not evidence.get('passed')or evidence['changed_files']!={n:r['current_sha256']for n,r in x['changes'].items()}:raise ValueError('Shared regression does not bind current interface')
    return x

def catalog_class(Base,config,project):
    if config.get('reviewed_native_listing_intake') is not None:
        from .admin_listing_intake import catalog_class as scoped_catalog
        return scoped_catalog(Base, config, project, legacy=catalog_class)
    if config.get('reviewed_shared_interface_intake')is None:return Base
    x=review(config,project)
    if config['source_task_id']!='986fe7a818c13d647950':raise ValueError('CSV intake scope differs')
    root=Path(project).resolve()
    class CurrentInterfaceCatalog(Base):
        def read(self,ref,*,raw=False):
            p=Path(ref['path'])
            if raw and p.is_relative_to(root):
                rel=p.relative_to(root).as_posix()
                if rel in x['changes']:
                    r=x['changes'][rel]
                    if ref['sha256']!=r['old_sha256']:raise ValueError('Historical CSV interface identity differs')
                    ref=dict(ref,sha256=r['current_sha256'])
            return super().read(ref,raw=raw)
    return CurrentInterfaceCatalog

def topic_driver(entry,project,output):
    runtime=json.loads((Path(project)/'configs/site-runtime-current.json').read_text())
    config=checked(runtime['retained_topic_registry'])
    if config.get('reviewed_shared_interface_intake')is None:return
    x=review(config,project);r=x['topic_driver'];p=Path(entry)/'topics2_normal_driver.py';index=Path(entry)/'entry-members.json'
    original=p.read_bytes()
    if hashlib.sha256(original).hexdigest()!=r['old_sha256']:raise ValueError('Historical Topic driver differs')
    old="profile.get('observation_policy') != 'full-if-fits-v1'"
    new="profile.get('observation_policy') not in ('full-if-fits-v1','full-lossless-rows-if-fits-v2')"
    text=original.decode()
    if text.count(old)!=1:raise ValueError('Exact Topic public-profile check required')
    revised=text.replace(old,new).encode()
    if hashlib.sha256(revised).hexdigest()!=r['current_sha256']:raise ValueError('Reviewed Topic profile adaptation differs')
    rows=json.loads(index.read_text())
    if rows['members'][p.name]!={'bytes':len(original),'sha256':r['old_sha256']}:raise ValueError('Original Topic entry index differs')
    p.write_bytes(revised);rows['members'][p.name]={'bytes':len(revised),'sha256':r['current_sha256']};index.write_text(json.dumps(rows,indent=2)+'\n')
    receipt=dict(original_driver_sha256=r['old_sha256'],current_driver_sha256=r['current_sha256'],only_public_profile_acceptance_changed=True,original_archive_preserved=True,review=config['reviewed_shared_interface_intake'])
    with(Path(output)/'public-interface-driver-update.json').open('x')as f:json.dump(receipt,f,indent=2);f.write('\n')
