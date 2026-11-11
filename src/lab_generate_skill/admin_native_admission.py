"""Reuse verified native completion evidence for a reviewed public goal revision.

This is a preparation gate, never an actor reward or a training admission.
The public goal can change only through the pinned definition; the actual
specification, target state, start state and native reset proof remain fixed.
"""
import hashlib
import json
from pathlib import Path
import tarfile

from .admin_pilot import bind, canonical_hash, evaluate

VERSION = 'admin-native-capability-admission-v1'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pinned(pin):
    path = Path(pin['path'])
    if digest(path) != pin['sha256']:
        raise ValueError('Reviewed admission input changed: ' + str(path))
    return json.loads(path.read_text())


def require(value, reason):
    if not value:
        raise ValueError(reason)


def load_native_admission(base, source_id, directory):
    base, directory = Path(base), Path(directory)
    certificate = json.loads((directory/'native-capability.json').read_text())
    require(certificate.get('version') == VERSION, 'Unknown native admission certificate')
    require(certificate.get('source_task_id') == source_id, 'Native admission source differs')
    project = (base/'code').resolve()
    require(digest(project/'configs/site-runtime-current.json') == certificate['runtime_pointer_sha256'],
            'Native admission must use its reviewed frozen runtime')
    definition = pinned(certificate['definition'])
    row = definition['source_row']
    rows = [json.loads(line) for line in (base/'tasks.jsonl').read_text().splitlines()]
    submitted_row = {**row, 'admission_path': str(directory/'result.json')}
    require([r for r in rows if r['source_task_id'] == source_id] == [submitted_row],
            'Submitted source row differs from reviewed public definition')
    require(row['kind'] == 'derived' and row['goal'] != row['source_goal'],
            'Revised goal must retain the original source mapping')
    original = pinned(certificate['original_admission'])
    require(original['task_id'] == source_id and original['passed'] is True,
            'Original native admission absent or failed')
    require(len(original['cycles']) == 2, 'Two original reset cycles required')
    initial_hash = canonical_hash(original['state'])
    for cycle in original['cycles']:
        restore = cycle['restore']
        require(cycle['controls'] >= 2 and restore['state_equal'] is True
                and restore['artifacts_restored'] is True and restore['state_hash'] == initial_hash,
                'Original control or complete reset evidence missing')
    review = pinned(certificate['native_review'])
    matches = [r for r in review['records'] if r['source_task_id'] == source_id]
    require(len(matches) == 1 and not review['unfinished_workers'], 'Complete native capability review required')
    verified = matches[0]
    require(verified['status'] == 'native_actor_interface_and_saved_state_verified'
            and verified['native_control_passed'] is True and verified['reset_verified'] is True,
            'Native actor-interface completion or reset not verified')
    archive = Path(verified['archive'])
    require(digest(archive) == verified['archive_sha256'], 'Native execution archive changed')
    prefix = 'diagnostics/' + source_id + '/'
    needed = ['binding.json', 'state-before.json', 'state-unsaved.json', 'state-after.json',
              'terminal-page.json', 'control-actions.jsonl']
    data = {}
    with tarfile.open(archive) as tar:
        for member in tar:
            if member.name not in {prefix+n for n in needed}:
                continue
            require(member.isfile() and member.name not in data, 'Duplicate/nonregular native evidence')
            data[member.name] = tar.extractfile(member).read()
    require(set(data) == {prefix+n for n in needed}, 'Missing native completion evidence')
    load = lambda name: json.loads(data[prefix+name])
    before, unsaved, after = (load(n) for n in ('state-before.json','state-unsaved.json','state-after.json'))
    require(canonical_hash(before) == initial_hash == canonical_hash(unsaved),
            'Current native baseline or unsaved-state evidence differs')
    native_binding = load('binding.json')
    binding = bind(row, before)
    require(binding['spec'] == native_binding['spec'] == original['binding']['spec'],
            'Goal revision changed the evaluated operation or target value')
    require(binding['start_path'] == native_binding['start_path'] == original['binding']['start_path'],
            'Goal revision changed the tested starting state')
    require(binding['goal'] == definition['goal'] and binding.get('runtime_task_id', source_id) == definition['runtime_task_id'],
            'Current binder changed the reviewed public goal or derived identity')
    require(binding['goal'] == row['goal'] and row['goal'] == definition['reviewed_public_goal'],
            'Public goal is not the reviewed definition')
    actions = [json.loads(line) for line in data[prefix+'control-actions.jsonl'].decode().splitlines()]
    require(actions and len(actions) == verified['action_count']
            and all(not a['error'] and not a['terminated'] and not a['truncated'] for a in actions),
            'Native actor-interface action sequence incomplete')
    terminal = load('terminal-page.json')
    test_binding = {**binding, 'site_netloc': native_binding['site_netloc']}
    require(evaluate(test_binding,before,after,terminal,'')['status'] == 'success',
            'Current evaluator rejects actual native completion')
    require(evaluate(test_binding,before,before,terminal,'')['status'] == 'failure'
            and evaluate(test_binding,before,unsaved,terminal,'')['status'] == 'failure',
            'Current evaluator accepts no-op or unsaved state')
    # Full public/native code equivalence is established by the pinned publisher;
    # historical actor outcomes are not promoted by these CPU controls.
    publication = pinned(certificate['compatibility'])
    require(publication['native_review'] == certificate['native_review']
            and publication['environment_reset_judge_and_task_definitions_unchanged'] is True,
            'Native capability proof is not bound to current code')
    current = json.loads((project/'configs/site-runtime-current.json').read_text())
    tested_files = {**publication['unchanged_files_sha256'], **publication['changed_files_sha256']}
    permitted = {'src/lab_generate_skill/admin_native_admission.py', 'scripts/report_admin_contract_batch.py'}
    changed = {n for n,h in current['actor_submission']['files_sha256'].items() if tested_files.get(n) != h}
    additional = changed - permitted
    removed = set(tested_files) - set(current['actor_submission']['files_sha256'])
    if additional or removed:
        from .admin_reviewed_native_runtime import verify_current_native_handoff
        verify_current_native_handoff(current, certificate, source_id, row, binding,
                                      original, publication)

    # The reviewed handoff rejects every removal outside its exact obsolete-file scope.
    for name, expected in current['actor_submission']['files_sha256'].items():
        require(digest(project/name) == expected, 'Frozen native runtime member changed: '+name)
    return {**original, 'binding': binding, 'state': before, 'training_admission': False,
            'current_native_capability': {'version':VERSION,'review':certificate['native_review'],
                'definition':certificate['definition'],'public_goal_revised':True,
                'historical_actor_result_promoted':False,'native_actions':len(actions)}}
