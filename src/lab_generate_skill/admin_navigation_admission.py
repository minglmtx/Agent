"""Portable admission of reviewed native navigation controls and baseline resets.

Control replay belongs to publication, not every rollout. A frozen registry
binds the exact reviewed operation, public goal, original proof and code bytes.
No actor result or success flag alone grants admission.
"""
import hashlib
import json
from pathlib import Path

from .admin_pilot import bind, canonical_hash

VERSION = 'admin-navigation-capability-v1'
REGISTRY_VERSION = 'admin-reviewed-navigation-runtime-v1'


def require(value, message):
    if not value:
        raise ValueError(message)


def read_pin(reference):
    raw = Path(reference['path']).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == reference['sha256'],
            'Navigation proof changed: ' + reference['path'])
    return json.loads(raw)


def load_navigation_admission(base, source_id, directory):
    base, directory = Path(base), Path(directory)
    certificate = json.loads((directory/'navigation-capability.json').read_text())
    require(certificate.get('version') == VERSION and certificate.get('source_task_id') == source_id,
            'Navigation certificate identity differs')
    project = (base/'code').resolve()
    runtime_bytes = (project/'configs/site-runtime-current.json').read_bytes()
    require(hashlib.sha256(runtime_bytes).hexdigest() == certificate['runtime_pointer_sha256'],
            'Navigation certificate belongs to a different frozen runtime')
    runtime = json.loads(runtime_bytes)
    reference = runtime.get('validation', {}).get('reviewed_admin_navigation_runtime')
    require(reference, 'Current navigation registry absent')
    registry = read_pin(reference)
    require(registry['version'] == REGISTRY_VERSION and registry['runtime_version'] == runtime['version'],
            'Navigation registry belongs to a different runtime')
    require(registry['runtime_files_sha256'] == runtime['actor_submission']['files_sha256'],
            'Navigation dependency closure differs')
    for relative, expected in registry['runtime_files_sha256'].items():
        require(hashlib.sha256((project/relative).read_bytes()).hexdigest() == expected,
                'Frozen navigation code changed: ' + relative)
    validation = read_pin(registry['publication_validation'])
    require(validation.get('passed') and validation['controls_review'] == registry['controls_review']
            and validation['shared_dependency_review'] == registry['shared_dependency_review']
            and validation['navigation_delta_review'] == registry['navigation_delta_review'],
            'Navigation publication validation incomplete')
    require(validation['tested_runtime_files_sha256'] == registry['runtime_files_sha256'],
            'Navigation runtime differs from tested code')
    # These compact reports establish which old dependencies changed and why
    # native navigation/reset evidence remains applicable to this exact build.
    controls = read_pin(registry['controls_review'])
    require(controls.get('scope') == len(registry['sources'])
            and not controls.get('statuses', {}).get('needs_specific_followup'),
            'Retained controls review incomplete')
    read_pin(registry['shared_dependency_review'])
    read_pin(registry['navigation_delta_review'])
    selected = [r for r in registry['sources'] if r['source_task_id'] == source_id]
    require(len(selected) == 1 and len({r['source_task_id'] for r in registry['sources']}) == len(registry['sources']),
            'Navigation source is not uniquely registered')
    entry = selected[0]
    require(source_id in validation['validated_sources'], 'Source lacks publication validation')
    row = entry['source_row']
    submitted = [json.loads(line) for line in (base/'tasks.jsonl').read_text().splitlines()]
    require([r for r in submitted if r.get('source_task_id') == source_id]
            == [{**row, 'admission_path': str(directory/'result.json')}],
            'Submitted navigation goal or source mapping differs')
    require(json.loads((directory/'result.json').read_text()) == entry['portable_result'],
            'Portable navigation result differs')
    original = read_pin(entry['original_admission'])
    require(original.get('task_id') == source_id and original.get('passed') is True,
            'Original native navigation controls failed or changed')
    state = original['state']
    require(canonical_hash(state) == entry['initial_state_sha256'] == original['snapshot']['state_hash'],
            'Navigation initial state differs')
    require(len(original['cycles']) == 2, 'Two complete reset cycles required')
    for i, cycle in enumerate(original['cycles']):
        restore = cycle['restore']
        require(cycle['cycle'] == i and restore['state_equal'] is True
                and restore['artifacts_restored'] is True
                and restore['state_hash'] == entry['initial_state_sha256']
                and restore['sha256'] == original['snapshot']['sha256'],
                'Original complete reset proof differs')
    binding = bind(row, state)
    require(binding['spec']['kind'] in ('page_navigation', 'menu_navigation'),
            'Non-navigation task cannot use navigation admission')
    require(binding['spec'] == original['binding']['spec'] == entry['spec']
            and binding['start_path'] == original['binding']['start_path'] == entry['start_path'],
            'Native operation, target or starting page changed')
    require(binding['goal'] == row['goal'] == entry['public_goal']
            and binding.get('runtime_task_id', source_id) == entry['runtime_task_id'],
            'Current binder differs from published navigation definition')
    require(canonical_hash(binding) == entry['binding_sha256'], 'Current binding differs')
    require(entry['retained_native_page_checks'] >= 6 and entry['original_reset_cycles'] == 2,
            'Native positive/negative/reset coverage incomplete')
    return {**original, 'binding': binding, 'training_admission': False,
            'current_navigation_capability': {'version': VERSION,
                'controls_review': registry['controls_review'],
                'retained_native_page_checks': entry['retained_native_page_checks'],
                'synthetic_checks': entry['synthetic_checks'],
                'native_controls_repeated_during_rollout': False,
                'actor_result_promoted': False}}
