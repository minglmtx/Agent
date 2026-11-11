"""Connect verified native source drivers to the ordinary batched actor runner.

The frozen bootstrap supplies the resolver, driver and original evidence.
Tasks cannot name import paths or substitute a control-only constructor. This
adapter adds no actions, observations, success criteria or model policy.
"""
from copy import deepcopy

from .source_revision_binding import require_source_binding


class FrozenNativeFamilyAdapter:
    def __init__(self, *, family, driver_key, resolver, public_goal,
                 feedback_versions, authorized_target_writes=False,
                 hook_protocol='private_reference', answer_fields=None,
                 proof_session=None, owns_csv_transport=False):
        families = (family,) if isinstance(family, str) else family
        if (not isinstance(families, tuple) or not families
                or any(not isinstance(value, str) or not value for value in families)
                or len(set(families)) != len(families)
                or not driver_key or not callable(resolver) or not callable(public_goal)):
            raise ValueError('Frozen driver binding and public renderer are required')
        if type(authorized_target_writes) is not bool or not feedback_versions:
            raise ValueError('Explicit write policy and feedback versions are required')
        if hook_protocol not in ('private_reference', 'private_reference_class',
                                 'full_admission_proof', 'raw_native_packet'):
            raise ValueError('An explicit supported ordinary hook protocol is required')
        if answer_fields is not None and not callable(answer_fields):
            raise ValueError('Public answer schema must be a trusted bootstrap callback')
        self.answer_fields = answer_fields
        if proof_session is not None:
            from .native_proof_session import NativeProofSession
            if not isinstance(proof_session, NativeProofSession):
                raise ValueError('A trusted live native proof session is required')
        self.proof_session = proof_session
        if type(owns_csv_transport) is not bool:
            raise ValueError('Explicit CSV transport ownership required')
        self.OWNS_NATIVE_CSV_TRANSPORT = owns_csv_transport
        self.hook_protocol = hook_protocol
        self.family = family
        self.families = frozenset(families)
        self.driver_key = driver_key
        self.resolve = resolver
        self.render = public_goal
        self.FEEDBACK_VERSIONS = tuple(feedback_versions)
        self.AUTHORIZED_TARGET_WRITES = authorized_target_writes

    def enabled(self, contract):
        return (contract.get('family') in self.families
                and contract.get('driver_key') == self.driver_key)

    def canonical(self, contract):
        if not self.enabled(contract):
            raise ValueError('Contract belongs to a different native family or driver')
        # The ordinary manifest adds only a private proof location. Every task
        # definition, public parameter and version field remains bound exactly.
        return deepcopy({k: v for k, v in contract.items() if k != 'admission_result'})

    def _verified_source(self, contract, descriptor):
        current = self.canonical(contract)
        source = self.resolve(current['source_task_id'], descriptor)
        if source['contract'] != current:
            raise ValueError('Current task differs from its verified native materialization')
        driver = source['driver']
        constructor = ('Hooks' if self.hook_protocol == 'private_reference_class' else
                       'make_hooks' if self.hook_protocol == 'private_reference' else 'create_hooks')
        if not callable(getattr(driver, constructor, None)):
            raise ValueError('Ordinary native hook constructor is unavailable')
        # Reuse the original full gate, including raw controls/reset/cleanup.
        # A successful descriptor or copied summary alone is not a proof.
        def verify():
            if source.get('version') in ('native-csv-retained-controls-reset-supplement-v1',
                                    'native-template-retained-controls-supplement-v1'):
                from pathlib import Path
                groups = source['groups']
                required = {str(Path(g[k]).resolve()) for g in groups
                            for k in ('controls_directory', 'supplement_directory')}
                # Include parent cleanup receipts in the live file-change guard.
                required.update(str(Path(g['controls_directory']).resolve().parent) for g in groups)
                roots = [Path(d).resolve() for d in source['directories']]
                if any(not any(Path(p).is_relative_to(root) for root in roots) for p in required):
                    raise ValueError('Supplement evidence not covered by proof change guard')
                verified = driver.require_supplement(current, groups)
            else:
                verified = driver.require_two_cold(current, source['cycles'], source['directories'])
            if verified != source['gate_return'] or verified.get('passed') is not True:
                raise ValueError('Original complete native gate result changed')
        if self.proof_session is not None:
            return self.proof_session.verify(current, descriptor, source, verify)
        verify()
        return source

    def require_admission(self, contract, descriptor):
        return self._verified_source(contract, descriptor)['gate_return']

    def require_original_binding(self, contract, original, inventory):
        return require_source_binding(self.canonical(contract), original, inventory,
                                      domain=contract['domain'])

    def NativeReadHooks(self, contract, descriptor, directory):
        source = self._verified_source(contract, descriptor)
        if self.hook_protocol == 'full_admission_proof':
            return source['driver'].create_hooks(self.canonical(contract),
                                                 source['gate_return'], directory)
        if self.hook_protocol == 'raw_native_packet':
            packet = source['native_packet']
            if packet.get('gate_return') != source['gate_return']:
                raise ValueError('Raw native packet differs from the complete verified gate')
            return source['driver'].create_hooks(self.canonical(contract), packet, directory)
        if source.get('version') in ('native-csv-retained-controls-reset-supplement-v1',
                                    'native-template-retained-controls-supplement-v1'):
            private = source['gate_return']['first_control']['private_reference']
        else:
            private = source['cycles'][0]['controls']['initial_no_op']['private_reference']
        # A non-null, original full proof selects the ordinary constructor path.
        # Never invoke make_hooks(..., proof=None), which is CPU-control only.
        constructor = (source['driver'].Hooks if self.hook_protocol == 'private_reference_class'
                       else source['driver'].make_hooks)
        return constructor(self.canonical(contract), private, directory, proof=source)

    def public_goal(self, contract):
        return self.render(self.canonical(contract))

    def fields(self, contract):
        public_contract = self.canonical(contract)
        if self.answer_fields is None:
            return []
        # No resolver, native reference or gate output enters the public schema.
        fields = self.answer_fields(public_contract)
        if (not isinstance(fields, (dict, list, tuple))
                or any(not isinstance(k, str) or not k.strip() for k in fields)
                or len(set(fields)) != len(fields)):
            raise ValueError('Public answer fields must be distinct nonempty names')
        if isinstance(fields, dict) and any(not isinstance(v, str) or not v.strip() for v in fields.values()):
            raise ValueError('Public answer fields require declared type names')
        return deepcopy(fields)

    def feedback(self, judgment):
        return {'status': judgment['status'], 'reward': judgment['reward'],
                'checks': {k: v for k, v in judgment.get('checks', {}).items()
                           if type(v) is bool},
                'private_reference_values_provided': False,
                'action_sequence_provided': False}
