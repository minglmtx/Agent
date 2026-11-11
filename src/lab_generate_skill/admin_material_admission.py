"""Bind a reviewed material revision to native saved-state and reset evidence.

A changed target value requires its own native save proof. An unchanged initial
state may reuse its previous reset cycles; neither proof grants actor success.
"""
import json
import tarfile
from pathlib import Path
from .admin_pilot import bind, canonical_hash, evaluate
from .admin_native_admission import pinned, require, digest

VERSION = 'admin-material-revision-admission-v1'


def load_material_admission(base, source_id, directory):
    base, directory = Path(base), Path(directory)
    certificate = json.loads((directory/'material-capability.json').read_text())
    require(certificate.get('version') == VERSION, 'Unknown material admission')
    require(certificate['source_task_id'] == source_id, 'Material source differs')
    project = (base/'code').resolve()
    current = json.loads((project/'configs/site-runtime-current.json').read_text())
    require(digest(project/'configs/site-runtime-current.json') == certificate['runtime_pointer_sha256'],
            'Material admission runtime differs')
    for name, expected in current['actor_submission']['files_sha256'].items():
        require(digest(project/name) == expected, 'Material dependency changed: '+name)
    definition = pinned(certificate['definition'])
    row = definition['source_row']
    require(row['source_task_id'] == source_id and row['kind'] == 'derived'
            and row['goal'] != row['source_goal'], 'Explicit derived source mapping required')
    rows = [json.loads(line) for line in (base/'tasks.jsonl').read_text().splitlines()]
    require([r for r in rows if r['source_task_id'] == source_id] ==
            [{**row, 'admission_path': str(directory/'result.json')}], 'Submitted material definition differs')
    receipt = pinned(certificate['native_receipt'])
    report = pinned(certificate['native_result'])
    verified = [r for r in report['records'] if r['source_task_id'] == source_id]
    require(len(verified) == 1, 'Unique material native result required')
    verified = verified[0]
    require(verified['native_completion'] is True and verified['readback_matches'] is True
            and verified['unsaved_rejected'] is True and not verified.get('error')
            and not verified.get('reset_error'), 'Native material save/readback incomplete')
    require(receipt['archive_sha256'] == certificate['archive_sha256']
            and digest(receipt['archive']) == receipt['archive_sha256'], 'Native material archive changed')
    paths = certificate['members']; data = {}
    require(set(paths) == {'before','after','unsaved','binding','terminal','actions'}, 'Incomplete material member map')
    require(len(set(paths.values())) == len(paths), 'Duplicate material member')
    with tarfile.open(receipt['archive']) as archive:
        for member in archive:
            if member.name not in paths.values():
                continue
            require(member.isfile() and member.name not in data, 'Duplicate/non-file material evidence')
            body = archive.extractfile(member).read()
            import hashlib
            require({'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()} == receipt['members'][member.name],
                    'Material evidence member changed')
            data[member.name] = body
    require(set(data) == set(paths.values()), 'Native material evidence missing')
    load = lambda key: json.loads(data[paths[key]])
    before, after, unsaved = (load(key) for key in ('before','after','unsaved'))
    native_binding, terminal = load('binding'), load('terminal')
    binding = bind(row,before)
    require(binding['spec'] == definition['expected_spec']
            and binding['spec']['kind'] == 'update'
            and binding['spec'].get('protect_unrelated_state') is True,
            'Unreviewed material evaluator specification')
    # The new protection condition adds checks; the native operation/value
    # itself must be exactly the one actually executed, never the old value.
    operation = {k:v for k,v in binding['spec'].items()
                 if k not in ('protect_unrelated_state','native_save_normalizations')}
    require(operation == native_binding['spec'], 'Native proof uses a different operation/value')
    for key in ('source_task_id','product_id','product_sku','product_name','scope_id','start_path','initial_value'):
        require(binding[key] == native_binding[key], 'Native material binding differs: '+key)
    require(binding['goal'] == definition['goal'] == row['goal'], 'Material public goal differs')
    require(binding['runtime_task_id'] == definition['runtime_task_id'], 'Derived material identity differs')
    original = pinned(certificate['reset_admission'])
    require(original['passed'] is True and original['task_id'] == source_id
            and original['state'] == before == unsaved, 'Material reset baseline differs')
    require(len(original['cycles']) == 2, 'Two existing reset cycles required')
    for cycle in original['cycles']:
        restore = cycle['restore']
        require(restore['state_equal'] is True and restore['artifacts_restored'] is True
                and restore['state_hash'] == canonical_hash(before), 'Existing reset proof incomplete')
    require(verified['database_reset']['state_equal'] is True
            and verified['database_reset']['state_hash'] == canonical_hash(before)
            and verified['database_reset']['artifacts_restored'] is True
            and verified['media_reset']['artifacts_restored'] is True, 'New material reset incomplete')
    actions = [json.loads(line) for line in data[paths['actions']].decode().splitlines()]
    require(actions and len(actions) == verified['actions']
            and all(not a.get('error') and not a.get('terminated') and not a.get('truncated') for a in actions),
            'Native material actions incomplete')
    test_binding = {**binding,'site_netloc':native_binding['site_netloc']}
    require(evaluate(test_binding,before,after,terminal,'')['status'] == 'success',
            'Current evaluator rejects saved material')
    for negative in (before,unsaved):
        require(evaluate(test_binding,before,negative,terminal,'')['status'] == 'failure',
                'Current evaluator accepts unsaved material')
    validation = pinned(certificate['guard_validation'])
    require(validation['passed'] is True and validation['archive_sha256'] == receipt['archive_sha256'],
            'Material guard validation missing')
    for relative, expected in validation['tested_files'].items():
        require(digest(project/relative) == expected, 'Material guard changed: '+relative)
    compatibility = pinned(certificate['compatibility'])
    require(compatibility['version'] == current['version']
            and compatibility['native_capsule'] == certificate['native_capsule']
            and compatibility['environment_actions_reset_unchanged'] is True,
            'Native capability not bound to current runtime')
    require(compatibility['current_files_sha256'] == current['actor_submission']['files_sha256'],
            'Material compatibility runtime differs')
    return {**original, 'binding':binding, 'state':before, 'training_admission':False,
            'current_material_capability': {'version':VERSION,'definition':certificate['definition'],
                 'native_receipt':certificate['native_receipt'],'native_actions':len(actions),
                 'historical_actor_result_promoted':False}}
