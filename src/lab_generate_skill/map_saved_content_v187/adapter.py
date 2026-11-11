"""Source-bound upload/diary adapter; reuse the qualified ordinary hooks."""
from copy import deepcopy
from .save_hooks import SaveHooks
from .save_judge import SOURCES, VERSION
from lab_generate_skill.source_revision_binding import require_source_binding, local_path
from lab_generate_skill.map_account_profile import validate_account

FAMILY = 'native_saved_content_v187'


def materialize(control, inventory):
    kind = next((k for k, sid in SOURCES.items() if sid == control.get('source_task_id')), None)
    if kind is None or inventory.get('task_id') != control['source_task_id'] or inventory.get('goal') != control['original_goal']:
        raise ValueError('Original saved-content source mapping differs')
    value = deepcopy(control)
    value.update(recorded_start_urls=deepcopy(inventory['recorded_start_urls']),
                 recorded_start_paths=[local_path(u) for u in inventory['recorded_start_urls']],
                 source_trace_ids=deepcopy(inventory['source_trace_ids']),
                 source_aliases=[control['source_task_id']], task_text_changed=True,
                 completion={}, candidate_completion=dict(family=FAMILY, kind=kind, version=VERSION),
                 goal_revision=dict(version=control['task_revision']['version'],
                     original_goal=control['original_goal'], derived_goal=control['goal'],
                     reason='Declare supplied local author, upload/content parameters and saved-record readback scope.',
                     equivalent_to_original_goal=False))
    require_source_binding(value, value, inventory, domain='map')
    return value


class SaveAdapter:
    FEEDBACK_VERSIONS = (VERSION,)
    AUTHORIZED_TARGET_WRITES = True

    def __init__(self, *, resolve_proof):
        if not callable(resolve_proof):
            raise ValueError('Verified source resolver required')
        self.resolve = resolve_proof

    def enabled(self, contract):
        return contract.get('domain') == 'map' and contract.get('candidate_completion', {}).get('family') == FAMILY

    def canonical(self, contract):
        if not self.enabled(contract):
            raise ValueError('Declared saved-content contract required')
        return deepcopy({k: v for k, v in contract.items() if k != 'admission_result'})

    def verified(self, contract, descriptor):
        candidate = self.canonical(contract)
        source = self.resolve(candidate['source_task_id'], descriptor)
        if source['candidate'] != candidate or source['admission']['passed'] is not True:
            raise ValueError('Saved-content task or admission differs')
        for key in ('native_controls_verified', 'ordinary_lifecycle_verified', 'full_cold_reset_verified', 'actual_public_input_verified'):
            if source['admission'].get(key) is not True:
                raise ValueError('Incomplete saved-content admission: ' + key)
        return source

    def require_admission(self, contract, descriptor):
        return deepcopy(self.verified(contract, descriptor)['admission'])

    def require_original_binding(self, contract, original, inventory):
        return require_source_binding(self.canonical(contract), original, inventory, domain='map')

    def NativeReadHooks(self, contract, descriptor, directory):
        source = self.verified(contract, descriptor)
        return SaveHooks(source['control_contract'], directory, baseline=source['baseline'])

    def public_goal(self, contract):
        return self.canonical(contract)['goal']

    def fields(self, contract):
        self.canonical(contract)
        return []

    def upload_files(self, contract, hooks):
        value = self.canonical(contract)
        if not isinstance(hooks, SaveHooks) or hooks.contract['source_task_id'] != value['source_task_id'] or hooks.contract['parameters'] != value['parameters']:
            raise ValueError('Upload assets require matching prepared source hooks')
        if value['source_task_id'] != SOURCES['upload']:
            return []
        from lab_generate_skill.browser_assets import BrowserUploadFile
        ref = value['parameters']['public_file']
        return [BrowserUploadFile(path=ref['path'], sha256=ref['sha256'], description='Supplied synthetic local training hike')]

    def profile_for_contracts(self, contracts):
        values = [self.canonical(c) for c in contracts]
        if not values or any(c['source_task_id'] not in SOURCES.values() for c in values):
            raise ValueError('Dedicated saved-content source manifest required')
        accounts = [validate_account(c['parameters']['account']) for c in values]
        if any(a != accounts[0] for a in accounts):
            raise ValueError('Saved-content account fixture differs')
        return dict(map_existing_account=accounts[0])

    def feedback(self, judgment):
        if judgment.get('version') != VERSION or judgment.get('status') not in ('success', 'failure', 'unknown'):
            raise ValueError('Qualified saved-content feedback required')
        return dict(status=judgment['status'], reward=judgment['reward'],
                    checks={k: v for k, v in judgment.get('checks', {}).items() if type(v) is bool},
                    private_reference_values_provided=False, action_sequence_provided=False)
