"""Apply a pinned native public environment revision to an owned frontend copy.

Only ordinary client capabilities change: actual OSRM alternative selection
and the real current directions URL in native long Share. No private source,
expected answer, evaluator state or actor repair enters the webpage.
"""
from pathlib import Path
import hashlib,json
from .io_utils import atomic_write_json
VERSION='map-native-route-public-capabilities-v1'


def apply_frontend_overlay(app, manifest, logs):
    app=Path(app).resolve();manifest=Path(manifest)
    value=json.loads(manifest.read_text())
    if(value.get('version')!=VERSION or value.get('official_snapshot_equivalence')is not False
       or value.get('private_task_state_access')is not False or len(value.get('members',{}))!=3):
        raise ValueError('Exact explicit public native environment revision required')
    package=Path(__file__).resolve().parents[2]
    prepared=[]
    for rel,row in value['members'].items():
        if Path(rel).is_absolute()or'..'in Path(rel).parts:raise ValueError('Ordinary native frontend member required')
        target=app/rel;source=package/row['candidate_member']
        if (target.is_symlink()or source.is_symlink()or not source.resolve().is_relative_to(package)
                or not target.resolve().is_relative_to(app)
                or any(a.is_symlink() for a in target.parents if a != app and a.is_relative_to(app))):
            raise ValueError('Native public frontend regular bytes required')
        old=target.read_bytes();new=source.read_bytes()
        if(len(old)!=row['original_bytes']or hashlib.sha256(old).hexdigest()!=row['original_sha256']
           or len(new)!=row['candidate_bytes']or hashlib.sha256(new).hexdigest()!=row['candidate_sha256']):
            raise ValueError('Complete native public source/candidate bytes changed: '+rel)
        prepared.append((target,new))
    for target,new in prepared:target.write_bytes(new)
    atomic_write_json(Path(logs)/'native-route-public-environment.json',{
        'version':VERSION,'official_snapshot_equivalence':False,'full_manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),
        'actual_public_files_applied':list(value['members']),'private_task_state_access':False,
        'expected_answer_in_page':False,'native_task_admissions':0})
    return VERSION
