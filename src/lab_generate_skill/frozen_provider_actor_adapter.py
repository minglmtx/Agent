"""Connect verified provider controls to the ordinary terminal-only actor path.

Only a frozen worker bootstrap supplies the original proof resolver. A task
cannot nominate imports, an environment constructor, or a private action plan.
The resolver owns evidence verification and its live file-change guard.
"""
from copy import deepcopy

from .map_provider_observation import ProviderObservationHooks
from .map_provider_terminal import VERSION, feedback
from .map_provider_contract import COMPARISON_FAMILY,validate_comparison
from .map_layer_comparison import LayerComparisonHooks,VERSION as COMPARISON_VERSION
from .source_revision_binding import require_source_binding


class FrozenProviderActorAdapter:
    FEEDBACK_VERSIONS = (VERSION,COMPARISON_VERSION)
    AUTHORIZED_TARGET_WRITES = False

    def __init__(self, *, resolve_proof):
        if not callable(resolve_proof):
            raise ValueError('Frozen original provider proof resolver required')
        self.resolve = resolve_proof

    def enabled(self, contract):
        return (contract.get('domain') == 'map'
                and 'ordered_export' not in contract
                and contract.get('candidate_completion', {}).get('family') in ('base_layer',COMPARISON_FAMILY))

    def canonical(self, contract):
        if not self.enabled(contract):
            raise ValueError('Native provider contract required')
        return deepcopy({k: v for k, v in contract.items() if k != 'admission_result'})

    def verified(self, contract, descriptor):
        candidate = self.canonical(contract)
        comparison=candidate['candidate_completion']['family']==COMPARISON_FAMILY
        if comparison:validate_comparison(candidate['candidate_completion'])
        source = self.resolve(candidate['source_task_id'], descriptor)
        version='native-layer-comparison-normal-admission-v1'if comparison else'native-provider-normal-admission-v1'
        if (source['candidate'] != candidate
                or source['admission'].get('version') != version
                or source['admission'].get('passed') is not True
                or source['admission'].get('two_cold_environment_verified') is not True
                or source['admission'].get('ordinary_lifecycle_verified') is not True
                or source['admission'].get('source_task_id') != candidate['source_task_id']
                or source['admission'].get('environment_binding') != source['environment_binding']
                or source['admission'].get('baseline') != source['baseline']
                or not isinstance(source['baseline'], str) or not source['baseline']):
            raise ValueError('Original provider task or complete admission differs')
        if comparison and (source['admission'].get('observed_pair_history_verified')is not True
                or source['admission'].get('single_layer_rejected')is not True
                or source['admission'].get('unverified_loading_not_rewarded')is not True):
            raise ValueError('Comparison-specific history and negative controls required')
        return source

    def require_admission(self, contract, descriptor):
        return deepcopy(self.verified(contract, descriptor)['admission'])

    def require_original_binding(self, contract, original, inventory):
        return require_source_binding(self.canonical(contract), original, inventory, domain='map')

    def NativeReadHooks(self, contract, descriptor, directory):
        source = self.verified(contract, descriptor)
        hook=LayerComparisonHooks if contract['candidate_completion']['family']==COMPARISON_FAMILY else ProviderObservationHooks
        return hook(self.canonical(contract), directory,
            environment_binding=source['environment_binding'], baseline=source['baseline'])

    def public_goal(self, contract):
        return self.canonical(contract)['goal']

    def fields(self, contract):
        self.canonical(contract)
        return []

    def feedback(self, judgment):
        if judgment.get('version')==COMPARISON_VERSION:
            return dict(status=judgment['status'],reward=judgment['reward'],
                checks=[dict(condition=k,passed=v)for k,v in judgment.get('checks',{}).items()if type(v)is bool],
                private_reference_values_provided=False,action_sequence_provided=False)
        return feedback(judgment)
