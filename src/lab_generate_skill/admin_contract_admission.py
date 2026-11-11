"""Portable admission of reviewed native contract controls and baseline resets.

Control replay belongs to publication, not every rollout. A frozen registry
binds the exact reviewed operation, public goal, original proof and code bytes.
Mutating controls reuse recorded saved-state checks under pinned scoring equivalence; absent intermediate state snapshots are not reconstructed. No actor result alone grants admission.
"""
import hashlib
import json
from pathlib import Path

from .admin_pilot import bind, canonical_hash

VERSION = 'admin-contract-capability-v1'
REGISTRY_VERSION = 'admin-reviewed-contract-runtime-v1'


def require(value, message):
    if not value:
        raise ValueError(message)


def read_pin(reference):
    raw = Path(reference['path']).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == reference['sha256'],
            'Contract proof changed: ' + reference['path'])
    return json.loads(raw)


def load_contract_admission(base, source_id, directory):
    base, directory = Path(base), Path(directory)
    certificate = json.loads((directory/'contract-capability.json').read_text())
    require(certificate.get('version') == VERSION and certificate.get('source_task_id') == source_id,
            'Contract certificate identity differs')
    project = (base/'code').resolve()
    runtime_bytes = (project/'configs/site-runtime-current.json').read_bytes()
    require(hashlib.sha256(runtime_bytes).hexdigest() == certificate['runtime_pointer_sha256'],
            'Contract certificate belongs to a different frozen runtime')
    runtime = json.loads(runtime_bytes)
    reference = runtime.get('validation', {}).get('reviewed_admin_contract_runtime')
    require(reference, 'Current contract registry absent')
    registry = read_pin(reference)
    require(registry['version'] == REGISTRY_VERSION and registry['runtime_version'] == runtime['version'],
            'Contract registry belongs to a different runtime')
    require(registry['runtime_files_sha256'] == runtime['actor_submission']['files_sha256'],
            'Contract dependency closure differs')
    for relative, expected in registry['runtime_files_sha256'].items():
        require(hashlib.sha256((project/relative).read_bytes()).hexdigest() == expected,
                'Frozen contract code changed: ' + relative)
    validation = read_pin(registry['publication_validation'])
    require(validation.get('passed') and validation['controls_review'] == registry['controls_review']
            and validation['shared_dependency_review'] == registry['shared_dependency_review']
            and validation['contract_delta_review'] == registry['contract_delta_review'],
            'Contract publication validation incomplete')
    require(validation['tested_runtime_files_sha256'] == registry['runtime_files_sha256'],
            'Contract runtime differs from tested code')
    # These compact reports establish which old dependencies changed and why
    # native contract/reset evidence remains applicable to this exact build.
    controls = read_pin(registry['controls_review'])
    require(controls.get('tasks') == len(registry['sources'])
            and not controls.get('statuses', {}).get('needs_specific_followup'),
            'Retained controls review incomplete')
    read_pin(registry['shared_dependency_review'])
    read_pin(registry['contract_delta_review'])
    selected = [r for r in registry['sources'] if r['source_task_id'] == source_id]
    require(len(selected) == 1 and len({r['source_task_id'] for r in registry['sources']}) == len(registry['sources']),
            'Contract source is not uniquely registered')
    entry = selected[0]
    require(source_id in validation['validated_sources'], 'Source lacks publication validation')
    row = entry['source_row']
    submitted = [json.loads(line) for line in (base/'tasks.jsonl').read_text().splitlines()]
    require([r for r in submitted if r.get('source_task_id') == source_id]
            == [{**row, 'admission_path': str(directory/'result.json')}],
            'Submitted contract goal or source mapping differs')
    require(json.loads((directory/'result.json').read_text()) == entry['portable_result'],
            'Portable contract result differs')
    original = read_pin(entry['original_admission'])
    require(original.get('task_id') == source_id and original.get('passed') is True,
            'Original native contract controls failed or changed')
    state = original['state']
    require(canonical_hash(state) == entry['initial_state_sha256'] == original['snapshot']['state_hash'],
            'Contract initial state differs')
    require(len(original['cycles']) == 2, 'Two complete reset cycles required')
    for i, cycle in enumerate(original['cycles']):
        restore = cycle['restore']
        require(cycle['cycle'] == i and restore['state_equal'] is True
                and restore['artifacts_restored'] is True
                and restore['state_hash'] == entry['initial_state_sha256']
                and restore['sha256'] == original['snapshot']['sha256'],
                'Original complete reset proof differs')
    binding = bind(row, state)
    if binding['spec']['kind'] != 'admin_contract':
        verify_classic_control_evidence(entry, binding, project)
    if binding['spec'].get('required_grid_operation'):
        verify_grid_operation_evidence(entry, binding, project)
    require(binding['spec'] == original['binding']['spec'] == entry['spec']
            and binding['start_path'] == original['binding']['start_path'] == entry['start_path'],
            'Native operation, target or starting page changed')
    require(binding['goal'] == row['goal'] == entry['public_goal']
            and binding.get('runtime_task_id', source_id) == entry['runtime_task_id'],
            'Current binder differs from published contract definition')
    require(canonical_hash(binding) == entry['binding_sha256'], 'Current binding differs')
    require(entry['retained_native_control_checks'] >= 4 and entry['original_reset_cycles'] == 2,
            'Native positive/negative/reset coverage incomplete')
    if binding['spec'].get('mode') in ('page_text_query', 'ui_query'):
        # Ordinary runtime verifies this initial reference against the new
        # initial page on reset; it must not be inferred from the terminal page.
        reference = original['binding'].get('query_reference')
        require(isinstance(reference, dict) and bool(reference),
                'Original public initial-page reference absent')
        binding = {**binding, 'query_reference': reference}
    return {**original, 'binding': binding, 'training_admission': False,
            'current_contract_capability': {'version': VERSION,
                'controls_review': registry['controls_review'],
                'retained_native_control_checks': entry['retained_native_control_checks'],
                'synthetic_checks': entry['synthetic_checks'],
                'native_controls_repeated_during_rollout': False,
                'actor_result_promoted': False}}


def verify_grid_operation_evidence(entry, binding, project):
    """Require repaired native operation controls in addition to answer checks."""
    if binding['spec'].get('mode') == 'ui_contract':
        return verify_ui_grid_operation_evidence(entry, binding, project)
    require(entry.get('grid_operation_review'), 'Native grid operation review absent')
    review = read_pin(entry['grid_operation_review'])
    require(review.get('passed') is True, 'Native grid operation review failed')
    selected = [r for r in review['records'] if r['source_task_id'] == entry['source_task_id']]
    require(len(selected) == 1, 'Grid operation source not uniquely reviewed')
    row = selected[0]
    require(row['original_admission'] == entry['original_admission']
            and row['spec'] == binding['spec'] and row['start_path'] == binding['start_path']
            and row['initial_state_sha256'] == entry['initial_state_sha256']
            and row['binding_sha256'] == entry['binding_sha256']
            and row['native_reset_cycles'] == 2,
            'Grid operation proof scope differs')
    required = {'correct_answer_without_operation': 'failure',
                'requested_grid_operation_applied': 'success',
                'operation_without_answer': 'failure',
                'wrong_answer_after_operation': 'failure'}
    for cycle in (0, 1):
        for name, status in required.items():
            cases = [r for r in row['current_evaluator_replays']
                     if r['cycle'] == cycle and r['name'] == name]
            require(len(cases) == 1 and cases[0]['passed'] is True
                    and cases[0]['status'] == status, 'Grid operation control missing or failed')
    expected = {'src/lab_generate_skill/admin_contract_rules.py',
                'src/lab_generate_skill/admin_grid_operation.py'}
    require(set(review['code_equivalence']) == expected, 'Grid evaluator dependency proof incomplete')
    for relative, evidence in review['code_equivalence'].items():
        equivalent=evidence['scoring_ast_identical'] is True
        if not equivalent:
            scope=read_pin(review['scoring_change_scope'])
            prior=read_pin(review['previous_review'])['code_equivalence'][relative]
            equivalent=(relative=='src/lab_generate_skill/admin_contract_rules.py'
                and binding['spec'].get('mode')!='navigate'
                and entry['source_task_id'] not in scope['affected_product_navigation_sources']
                and scope['passed'] and prior['scoring_ast_identical'] is True
                and prior['current_sha256']==scope['old_source_sha256'][relative]
                and evidence['current_sha256']==scope['new_source_sha256'][relative]
                and evidence.get('applicable_non_navigation_scoring_ast_identical') is True)
        require(equivalent and
                hashlib.sha256((project / relative).read_bytes()).hexdigest() == evidence['current_sha256'],
                'Grid evaluator changed since native proof review')


def verify_classic_control_evidence(entry, binding, project):
    """Accept only bounded classic kinds with pinned real-operation proof."""
    require(binding['spec']['kind'] in ('navigation','update','comment','typed_query','query'),
            'Classic kind lacks real-operation admission')
    ref=entry.get('classic_control_review')
    require(ref, 'Classic native-control review absent')
    review=read_pin(ref)
    require(review.get('passed') is True, 'Classic review failed')
    matches=[r for r in review['records'] if r['source_task_id']==entry['source_task_id']]
    require(len(matches)==1, 'Classic source not uniquely reviewed')
    record=matches[0]
    require(record['status']=='retained_native_controls_compatible_entry_binding_pending'
            and record['native_positive_proven'] is True and record['reset_cycles']==2,
            'Classic real positive/reset evidence incomplete')
    for key in ('source_row','spec','start_path','public_goal','runtime_task_id',
                'binding_sha256','original_admission','initial_state_sha256'):
        require(record[key]==entry[key], 'Classic reviewed binding differs: '+key)
    scope=read_pin(review['scoring_change_scope'])
    require(scope['passed'] and scope['classic_12_scoring_unchanged'], 'Classic scoring scope unverified')
    read_pin(review['previous_review'])
    if binding['spec']['kind']=='query':
        native=record.get('native_query_review',{})
        require(native.get('status')=='native_validation_supported' and native.get('spec')==binding['spec']
                and native.get('goal')==binding['goal'] and native.get('reset_cycles')==2,
                'Query lacks real browser positive/reset proof')
        require(len(native.get('positive_observations',[]))==2
                and all(x.get('actual_ui_value') for x in native['positive_observations']),
                'Query real UI values absent')
        require(native['source_hashes']['src/lab_generate_skill/admin_pilot.py']==scope['new_source_sha256']['src/lab_generate_skill/admin_pilot.py'],
                'Query native test used a different evaluator')
    for name,expected in review['tested_scoring_files'].items():
        require(hashlib.sha256((project/name).read_bytes()).hexdigest()==expected,
                'Classic applicable scoring has not been reviewed: '+name)
    require(record['native_control_results']==entry['retained_native_control_checks'],
            'Classic control count differs')
    read_pin(review['controls_summary'])
    read_pin(review['input_pins'])


def verify_ui_grid_operation_evidence(entry, binding, project):
    """Admit operation-only UI tasks using real controls and scoped negatives.

    Query-plus-answer tasks retain their independent answer-control protocol.
    A declared empty search is still an operation, not evidence of submission.
    """
    require(binding['spec'].get('mode') == 'ui_contract'
            and binding['spec'].get('required_grid_operation')
            and binding['spec'].get('required_final_path')
            and binding['spec'].get('ui_expected'),
            'UI grid contract lacks explicit operation, target or public values')
    require(entry.get('grid_operation_review'), 'Native grid operation review absent')
    review = read_pin(entry['grid_operation_review'])
    require(review.get('version') == 'admin-ui-grid-native-review-v1'
            and review.get('passed') is True, 'UI grid operation review failed')
    selected = [r for r in review['records'] if r['source_task_id'] == entry['source_task_id']]
    require(len(selected) == 1, 'UI grid operation source not uniquely reviewed')
    row = selected[0]
    require(row['original_admission'] == entry['original_admission']
            and row['spec'] == binding['spec'] and row['start_path'] == binding['start_path']
            and row['initial_state_sha256'] == entry['initial_state_sha256']
            and row['binding_sha256'] == entry['binding_sha256']
            and row['native_reset_cycles'] == 2, 'UI grid operation proof scope differs')
    required = {
        'initial_state_unchanged': ('failure', 'native_page'),
        'requested_grid_operation_applied': ('success', 'native_page'),
        'typed_value_without_request': ('failure', 'synthetic_evaluator_input'),
        'response_not_applied': ('failure', 'synthetic_evaluator_input'),
        'wrong_grid_parameters': ('failure', 'synthetic_evaluator_input'),
    }
    for cycle in (0, 1):
        for name, (status, control_type) in required.items():
            cases = [r for r in row['current_evaluator_replays']
                     if r['cycle'] == cycle and r['name'] == name]
            require(len(cases) == 1 and cases[0]['passed'] is True
                    and cases[0]['status'] == status
                    and cases[0]['control_type'] == control_type
                    and bool(cases[0].get('source_page')),
                    'UI grid operation control missing or failed')
    expected = {'src/lab_generate_skill/admin_contract_rules.py',
                'src/lab_generate_skill/admin_grid_operation.py',
                'src/lab_generate_skill/admin_ui_contract.py',
                'src/lab_generate_skill/admin_pilot.py'}
    require(set(review['tested_scoring_files']) == expected,
            'UI grid evaluator dependency proof incomplete')
    for relative, expected_hash in review['tested_scoring_files'].items():
        require(hashlib.sha256((project / relative).read_bytes()).hexdigest() == expected_hash,
                'UI grid evaluator changed since native proof review')
