"""Source-bound ordinary adapter for explicitly declared local reader tasks."""
from copy import deepcopy
from .hooks import ReaderHooks, SOURCES
from .rss_client import VERSION as RSS_VERSION
from .diary_read import VERSION as NY_VERSION
from .profile import profile_for_contracts
from lab_generate_skill.source_revision_binding import require_source_binding, local_path

FAMILY = 'native_reader_diaries_v187'


def materialize(control, inventory):
    sid = control.get('source_task_id')
    if sid not in SOURCES or inventory.get('task_id') != sid or inventory.get('goal') != control['original_goal']:
        raise ValueError('Original reader/diary source mapping differs')
    value = deepcopy(control)
    value.update(recorded_start_urls=deepcopy(inventory['recorded_start_urls']),
        recorded_start_paths=[local_path(u) for u in inventory['recorded_start_urls']],
        source_trace_ids=deepcopy(inventory['source_trace_ids']),
        source_aliases=[sid], heldout_quarantine=inventory['heldout_quarantine'], task_text_changed=True,
        completion={}, candidate_completion=dict(family=FAMILY, kind=SOURCES[sid], version=control['version']),
        goal_revision=dict(version=control['version'], original_goal=control['original_goal'],
            derived_goal=control['goal'], equivalent_to_original_goal=False,
            reason='Declare the supplied local reader and synthetic geographic diary fixture with task-specific completion scope.'))
    if value['start_path'] != value['recorded_start_paths'][0]:
        if value['start_path'] not in value['recorded_start_paths']:
            raise ValueError('Start must be an actual recorded original source frame')
        value['start_revision'] = dict(version='captured-original-frame-selection-v187',
            original_start=value['recorded_start_paths'][0], derived_start=value['start_path'],
            reason='Use the audited original first browser observation; retain the inventory default URL and every source trace.',
            equivalent_to_original_start=False)
    require_source_binding(value, value, inventory, domain='map')
    return value


class ReaderAdapter:
    FEEDBACK_VERSIONS = (RSS_VERSION, NY_VERSION)
    # Reader writes are bounded by ReaderHooks; NY requires complete immutability.
    AUTHORIZED_TARGET_WRITES = True

    def __init__(self, *, resolve_proof):
        if not callable(resolve_proof):
            raise ValueError('Verified source resolver required')
        self.resolve = resolve_proof

    def enabled(self, contract):
        return contract.get('domain') == 'map' and contract.get('candidate_completion', {}).get('family') == FAMILY

    def canonical(self, contract):
        if not self.enabled(contract):
            raise ValueError('Declared reader/diary source contract required')
        return deepcopy({k: v for k, v in contract.items() if k != 'admission_result'})

    def verified(self, contract, descriptor):
        candidate = self.canonical(contract)
        source = self.resolve(candidate['source_task_id'], descriptor)
        if source['candidate'] != candidate or source['admission']['passed'] is not True:
            raise ValueError('Reader/diary task or admission differs')
        for key in ('native_controls_verified', 'ordinary_lifecycle_verified', 'full_cold_reset_verified', 'actual_public_input_verified'):
            if source['admission'].get(key) is not True:
                raise ValueError('Incomplete reader/diary admission: ' + key)
        return source

    def require_admission(self, contract, descriptor):
        return deepcopy(self.verified(contract, descriptor)['admission'])

    def require_original_binding(self, contract, original, inventory):
        return require_source_binding(self.canonical(contract), original, inventory, domain='map')

    def NativeReadHooks(self, contract, descriptor, directory):
        source = self.verified(contract, descriptor)
        return ReaderHooks(source['control_contract'], directory, baseline=source['baseline'])

    def public_goal(self, contract):
        return self.canonical(contract)['goal']

    def fields(self, contract):
        self.canonical(contract)
        return []

    def profile_for_contracts(self, contracts):
        return profile_for_contracts([self.canonical(c) for c in contracts])

    def feedback(self, judgment):
        if judgment.get('version') not in self.FEEDBACK_VERSIONS or judgment.get('status') not in ('success', 'failure', 'unknown'):
            raise ValueError('Qualified reader/diary feedback required')
        return dict(status=judgment['status'], reward=judgment['reward'],
            checks={k: v for k, v in judgment.get('checks', {}).items() if type(v) is bool},
            private_reference_values_provided=False, action_sequence_provided=False)
