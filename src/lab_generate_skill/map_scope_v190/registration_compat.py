"""Narrow dependency update for the unchanged registration source."""
from pathlib import Path
import hashlib, json

NAMES = frozenset([
    'configs/admin-completion-contracts-v1.json', 'configs/admin-navigation-extension-v1.json',
    'scripts/admin_pilot_controls.py', 'scripts/experiment_admin_admission.py',
    'scripts/map_surfaces/offline-review.json',
] + ['src/lab_generate_skill/' + n + '.py' for n in (
    'admin_pilot', 'admin_public_contract', 'admin_ui_contract',
    'map_frozen_provider_runtime', 'map_provider_contract', 'map_provider_environment',
    'map_provider_resources', 'reviewed_map_registry', 'public_interface_intake', 'admin_category_admission', 'admin_native_mutation_admission', 'admin_reviewed_operation_admission')])

REGISTRY_ADDITIONS = (
    b"    'gps_document_v190': ('map_scope_v190.catalog', 'GPSCatalog', 'map_scope_v190.adapter', 'GPSAdapter'),\n",
    b"    'public_overlays_v190': ('map_scope_v190.catalog', 'LayerCatalog', 'map_scope_v190.adapter', 'LayerAdapter'),\n",
)
SPLIT_NEW = b'''                    if kind == 'public_overlays_v190':
                        # Keep the exact executed candidate schema. Its training
                        # split is checked against pinned original source records.
                        if catalog.sources[sid].get('training_source_verified') is not True:
                            raise ValueError('Reviewed overlay training source proof required')
                    elif row.get('split') != 'train' or row.get('heldout_quarantine'):
'''
SPLIT_OLD = b"                    if row.get('split') != 'train' or row.get('heldout_quarantine'):\n"
PROFILE_NEW = b'''                    if kind == 'gps_document_v190':
                        extra.extend(['--map-native-provider-manifest', catalog.config['profile']['path']])
'''

def previous_registry(raw):
    for addition in REGISTRY_ADDITIONS:
        if raw.count(addition) != 1:
            raise ValueError('Exact new scope family declaration required')
        raw = raw.replace(addition, b'')
    if raw.count(SPLIT_NEW) != 1 or raw.count(PROFILE_NEW) != 1:
        raise ValueError('Exact new-family split and startup branches required')
    return raw.replace(SPLIT_NEW, SPLIT_OLD).replace(PROFILE_NEW, b'')

def require_update(update, *, source, project, read):
    if (update.get('version') != 'registration-native-scope-compatibility-v190'
            or update.get('source_task_id') != source or update.get('passed') is not True
            or set(update.get('changes', {})) != NAMES):
        raise ValueError('Exact registration source and unrelated scope delta required')
    shared = read(update['shared_review'])
    provider = read(update['provider_isolation_review'])
    admission = read(update['admission_isolation_review'])
    if (not shared.get('passed') or shared.get('unchanged_existing_admin_specs') != 451
            or shared.get('intentionally_revised_admin_bindings') != 5
            or not shared.get('old_map_registry_dispatch_ast_preserved')
            or not provider.get('passed') or not provider.get('old_frontend_bytes_identical')
            or not provider.get('new_gps_frontend_matches_executed_candidate')
            or not admission.get('passed') or not admission.get('old_admission_program_ast_identical')
            or not admission.get('new_listing_program_ast_identical_to_executed_candidate')):
        raise ValueError('Native scope isolation evidence incomplete')
    project = Path(project)
    for name, change in update['changes'].items():
        before = read(change['previous_file'], json_value=False)
        if hashlib.sha256(before).hexdigest() != change['previous_sha256']:
            raise ValueError('Previous registered dependency identity differs')
        current = read(dict(path=str(project / name), sha256=change['current_sha256']), json_value=False)
        if name == 'src/lab_generate_skill/reviewed_map_registry.py':
            if previous_registry(current) != before:
                raise ValueError('Existing registration dispatch was modified')
        elif name == 'scripts/map_surfaces/offline-review.json':
            expected = json.loads(before)
            rows = [r for r in expected['reused_runtime_files'] if Path(r['path']).name == 'admin_pilot.py']
            if len(rows) != 1:
                raise ValueError('Exact reused Admin runtime metadata row required')
            delta = update['changes']['src/lab_generate_skill/admin_pilot.py']
            if rows[0]['sha256'] != delta['previous_sha256']:
                raise ValueError('Surface metadata does not name the reviewed previous runtime')
            rows[0]['sha256'] = delta['current_sha256']
            if json.loads(current) != expected:
                raise ValueError('Surface offline review changed beyond the verified runtime pin')
        else:
            if current != read(change['qualified_current_file'], json_value=False):
                raise ValueError('Dependency differs from reviewed native scope candidate')
    for name, digest in provider['tested_current_files'].items():
        read(dict(path=str(project / name), sha256=digest), json_value=False)
    for name, digest in admission['tested_current_files'].items():
        read(dict(path=str(project / name), sha256=digest), json_value=False)
    return update['changes']
