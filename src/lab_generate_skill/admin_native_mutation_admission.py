"""Use reviewed real mutation controls in the ordinary Admin entry.

Only the runtime-bound source list is accepted. Evidence is read once per
worker, shared across tasks, and rechecked for changes before reuse. This
validates preparation; Actor completion is still evaluated independently.
"""
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import tarfile
from urllib.parse import urlsplit

VERSION = 'admin-native-mutation-capability-v1'


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _identity(path):
    stat = Path(path).stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


@lru_cache(maxsize=2)
def _review(project, review_path, review_hash, runtime_hash):
    from .admin_pilot import bind, evaluate
    from .admin_native_mutation import combine, runtime_id
    project = Path(project)
    identities = {}

    def pinned(ref, json_value=True):
        path = Path(ref['path']); before = _identity(path); raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != ref['sha256'] or _identity(path) != before:
            raise ValueError('Native mutation evidence changed: ' + str(path))
        identities[str(path)] = before
        return json.loads(raw) if json_value else raw

    report = pinned(dict(path=review_path, sha256=review_hash))
    prep = pinned(report['preparation'])
    if (report.get('passed') is not True or report.get('sources') != 4
            or report.get('control_replays') != 72
            or not report.get('old_default_capture_body_unchanged')
            or not report.get('public_goal_and_start_verified')):
        raise ValueError('Complete ordinary mutation replay review required')
    for name, ref in prep['changes'].items():
        if pinned(ref, False) != (project/name).read_bytes():
            from .admin_operation_scope_compat import require_change
            identities.update(require_change(project, 'native_mutation', name, ref))
    original_reviews = [pinned(ref) for ref in prep['source_reviews']]
    valid = [r for rev in original_reviews for r in rev['records'] if r['passed']]
    contracts = {c['source_task_id']: c for c in json.loads((project/'configs/admin-native-mutations-v1.json').read_text())['tasks']}
    records = report['records']
    if len(records) != len(contracts) or {r['source_task_id'] for r in records} != set(contracts):
        raise ValueError('Native mutation source coverage changed')
    archives = {}; results = {}; total = 0
    for row in records:
        sid = row['source_task_id']; c = contracts[sid]; native = row['native_review']
        if native not in valid:
            raise ValueError('Missing original successful native control cycle')
        ref = native['archive']; path = ref['path']
        if path not in archives:
            pinned(ref, False); index = pinned(native['archive_index'])['members']; data = {}; seen = set()
            with tarfile.open(path, 'r|gz') as handle:
                for member in handle:
                    if not member.isfile() or member.name in seen or member.name not in index:
                        raise ValueError('Unexpected native mutation archive member')
                    raw = handle.extractfile(member).read(); seen.add(member.name)
                    if index[member.name] != dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()):
                        raise ValueError('Native mutation archive content changed')
                    if member.name.endswith('.json'): data[member.name] = json.loads(raw)
            if seen != set(index): raise ValueError('Incomplete native mutation evidence')
            archives[path] = data
        data = archives[path]; before = combine(data['initial-state.json']); source = row['source_row']
        expected_source = dict(source_task_id=sid,goal=c['goal'],source_goal=c['original_goal'],
                               kind='derived' if c['derived'] else 'original',runtime_task_id=runtime_id(c))
        if source != expected_source: raise ValueError('Public native mutation definition changed')
        binding = bind(source,before)
        if binding != row['binding'] or binding['start_path'] != c['declared_local_start_path']:
            raise ValueError('Native mutation goal or start changed')
        count = 0
        for i in range(2):
            folder=f'sources/{sid}/{i}'; cycle=data[folder+'/result.json']; reset=cycle['restore']
            if (not cycle['passed'] or reset.get('native_extra_state_equal') is not True
                    or reset.get('state_equal') is not True or reset.get('artifacts_restored') is not True):
                raise ValueError('Full native mutation reset proof required')
            start=urlsplit(data[folder+'/browser/original-start-page.json']['url'])
            if start.path != '/admin'+c['declared_local_start_path']:
                raise ValueError('Original native mutation start differs')
            local=dict(binding,site_netloc=start.netloc)
            for name, control in cycle['controls'].items():
                if not control['synthetic']:
                    label={'native_saved_operation':'saved'}.get(name,name)
                    state=deepcopy(data[folder+'/'+label+'-state.json']);page=deepcopy(data[folder+'/'+label+'-page.json'])
                else:
                    state=deepcopy(data[folder+'/saved-state.json']);page=deepcopy(data[folder+'/saved-page.json'])
                    if name=='wrong_site':page['url']='http://wrong.invalid/admin/'
                    elif name=='error_page':page['page_error']=True
                    elif name=='login_page':page['login']=True
                    elif name=='missing_native_evidence':del state['native']
                    elif name=='wrong_scope_or_content':state=deepcopy(data[folder+'/wrong-state.json'])
                    else:raise ValueError('Unknown native mutation control')
                after=combine(state) if 'native' in state else state['base']
                score=evaluate(local,before,after,page,'')
                if score['status'] != control['expected'] or score['reward'] != control['actual']['reward']:
                    raise ValueError('Current native mutation control differs: '+name)
                count+=1
        if count != row['control_replays']: raise ValueError('Native mutation control coverage differs')
        total+=count
        results[sid]=dict(task_id=sid,passed=True,binding=binding,state=before,source_row=source,
                         training_admission=False,native_control_replays=count,full_reset_cycles=2,
                         independent_cold_starts_claimed=False)
    if total != report['control_replays']: raise ValueError('Missing native mutation control cases')
    return results,identities


def load_native_mutation_admission(base, source_id, directory):
    base, directory = Path(base), Path(directory)
    cert=json.loads((directory/'native-mutation-capability.json').read_text())
    project=(base/'code').resolve(); runtime_file=project/'configs/site-runtime-current.json'
    runtime=json.loads(runtime_file.read_text()); runtime_hash=_hash(runtime_file)
    if (cert.get('version') != VERSION or cert.get('source_task_id') != source_id
            or cert.get('runtime_pointer_sha256') != runtime_hash
            or cert.get('review') != runtime.get('validation',{}).get('native_mutation_review')):
        raise ValueError('Exact frozen native mutation admission binding required')
    # Frozen code identity is checked without consulting a writable live project.
    for name,value in runtime['actor_submission']['files_sha256'].items():
        if _hash(project/name) != value: raise ValueError('Frozen runtime member changed: '+name)
    results,identities=_review(str(project),cert['review']['path'],cert['review']['sha256'],runtime_hash)
    if source_id not in results or any(_identity(p)!=identity for p,identity in identities.items()):
        raise ValueError('Native mutation source or retained evidence changed')
    result=deepcopy(results[source_id]); rows=[json.loads(x)for x in (base/'tasks.jsonl').read_text().splitlines()]
    if [r for r in rows if r['source_task_id']==source_id] != [{**result['source_row'],'admission_path':str(directory/'result.json')}]:
        raise ValueError('Submitted native mutation source differs')
    return result
