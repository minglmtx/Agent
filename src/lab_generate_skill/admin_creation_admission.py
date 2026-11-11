"""Reuse a native material completion proof; never reuse an actor's label."""
import hashlib,json,tarfile
from pathlib import Path
from .admin_native_admission import pinned,require,digest
from .admin_pilot import bind,canonical_hash,evaluate
from .admin_material_creation import material_definition,description_images,VERSION

def load_creation_admission(base,source,directory):
    base,directory=Path(base),Path(directory);project=base/'code'
    c=json.loads((directory/'creation-capability.json').read_text())
    require(c['version']==VERSION and c['source_task_id']==source,'Wrong creation capability')
    runtime=json.loads((project/'configs/site-runtime-current.json').read_text())
    require(digest(project/'configs/site-runtime-current.json')==c['runtime_pointer_sha256'],'Creation runtime changed')
    for name,h in runtime['actor_submission']['files_sha256'].items():require(digest(project/name)==h,'Creation dependency changed: '+name)
    definition=pinned(c['definition']);canonical=material_definition(source)
    require(canonical is not None,'Creation source unregistered')
    for key in canonical:require(definition[key]==canonical[key],'Creation definition differs: '+key)
    row=definition['source_row'];rows=[json.loads(l)for l in (base/'tasks.jsonl').read_text().splitlines()]
    require([r for r in rows if r['source_task_id']==source]==[{**row,'admission_path':str(directory/'result.json')}],'Submitted creation contract differs')
    receipt=pinned(c['native_receipt']);report=pinned(c['native_result']);plan=pinned(c['native_plan'])
    require(receipt['returncode']==0 and receipt['plan_sha256']==c['native_plan']['sha256'],'Native run incomplete')
    require(plan['capsule']==c['native_capsule'],'Native capsule differs')
    for path,h in plan['input_sha256'].items():require(digest(path)==h,'Native proof input changed')
    materials=json.loads(Path(plan['materials']).read_text());material=canonical['material']
    for key,value in materials['coffee'].items():require(material[key]==value,'Native material differs: '+key)
    require(material['native_renderer_sha256']==plan['native_filter_source_sha256'],'Native renderer differs')
    require(canonical['fixture_source_id']==materials['short']['source_task_id'],'Undeclared fixture change')
    records=[r for r in report['records']if r['source_task_id']==source];require(len(records)==1,'Unique native result required');record=records[0]
    require(record['native_completion'] and record['unsaved_rejected'] and record['fresh_readback_matches'] and record['saved_image_reloaded'] and not record.get('error') and not record.get('reset_error'),'Native readback incomplete')
    require(digest(receipt['archive'])==receipt['archive_sha256'],'Native archive changed')
    data={}
    with tarfile.open(receipt['archive'])as archive:
        for member in archive:
            require(member.isfile() and member.name not in data,'Duplicate/non-file native evidence')
            body=archive.extractfile(member).read();require(receipt['members'][member.name]==dict(bytes=len(body),sha256=hashlib.sha256(body).hexdigest()),'Native member mismatch');data[member.name]=body
    require(set(data)==set(receipt['members']),'Native members missing')
    get=lambda name:json.loads(data['diagnostics/'+name])
    before,after,unsaved=get('cold-state.json'),get('coffee/saved-state.json'),get('coffee/unsaved-state.json')
    native_binding=get('coffee/candidate-binding.json');binding=bind(row,before)
    require(binding['spec']==definition['expected_spec'] and binding['start_path']==native_binding['start_path'],'Creation binding differs')
    require(binding['runtime_task_id']==canonical['runtime_task_id'],'Derived identity differs')
    original=pinned(c['reset_admission']);require(original['passed'] and original['task_id']==canonical['fixture_source_id'] and original['state']==before==unsaved,'Creation baseline differs')
    require(len(original['cycles'])==2,'Existing reset proof requires two cycles')
    for cycle in original['cycles']:
        restore=cycle['restore'];require(restore['state_equal'] and restore['artifacts_restored'] and restore['state_hash']==canonical_hash(before),'Existing reset incomplete')
    restore=record['database_reset'];require(restore['state_equal'] and restore['artifacts_restored'] and restore['state_hash']==canonical_hash(before) and record['media_reset']['artifacts_restored'],'Creation reset incomplete')
    actions=[json.loads(l)for l in data['diagnostics/coffee/control-actions.jsonl'].decode().splitlines()]
    require(len(actions)==record['actions'] and all(not r.get('error') and not r.get('terminated') and not r.get('truncated')for r in actions),'Native actions incomplete')
    image=get('coffee/persisted-image.json');require(image['matched'] and image['sha256']==material['image_sha256'],'Native image differs')
    require(all(get('coffee/native-component-readback.json').values()),'Native saved component readback incomplete')
    dimensions=get('coffee/fresh-image-load.json');require(dimensions['complete'] and dimensions['width']>0 and dimensions['height']>0,'Native image did not load')
    target=next(p for p in after['records']['product']if p['sku']==material['sku']);description=target['description'];refs=description_images(description)
    require(refs and set(refs)=={image['path_relative_to_media']},'Native image proof covers different references')
    page=get('coffee/terminal-page.json');page['material_creation']=dict(version=VERSION,target_count=1,entity_id=target['entity_id'],description_sha256=hashlib.sha256(description.encode()).hexdigest(),native_renderer=get('coffee/native-render.json'),images=[dict(reference=r,status='read',sha256=image['sha256'])for r in refs])
    test_binding={**binding,'site_netloc':native_binding['site_netloc']}
    require(evaluate(test_binding,before,after,page,'')['status']=='success','Current creation evaluator rejects native completion')
    for negative in (before,unsaved):require(evaluate(test_binding,before,negative,page,'')['status']=='failure','Creation evaluator accepts no-op/unsaved')
    validation=pinned(c['validation']);require(validation['passed'] and validation['archive_sha256']==receipt['archive_sha256'],'Creation tests missing')
    for name,h in validation['tested_files'].items():require(digest(project/name)==h,'Creation tested code changed')
    compatibility=pinned(c['compatibility'])
    require(compatibility['version']==runtime['version'] and compatibility['current_files_sha256']==runtime['actor_submission']['files_sha256'] and compatibility['native_capsule']==c['native_capsule'] and compatibility['environment_actions_reset_unchanged'],'Creation compatibility missing')
    return {**original,'task_id':source,'binding':binding,'state':before,'training_admission':False,
            'current_material_capability':dict(version=VERSION,definition=c['definition'],native_receipt=c['native_receipt'],native_actions=len(actions),historical_actor_result_promoted=False)}
