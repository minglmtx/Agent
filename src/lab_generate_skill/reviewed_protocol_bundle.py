"""One dispatch registration for already verified, source-bound adapters.

The trusted runtime bootstrap supplies adapters and their canonical contracts.
This class never imports task-selected code or grants admission itself. Each
operation still uses the original adapter and its original proof resolver.
"""
from copy import deepcopy


class ReviewedProtocolBundle:
    def __init__(self, bindings):
        self._sources = {}
        self._adapters = []
        self._feedback = {}
        policies = set()
        csv_owners = set()
        for adapter, contracts in bindings:
            required = ('enabled', 'require_admission', 'require_original_binding',
                        'NativeReadHooks', 'public_goal', 'fields', 'feedback')
            if any(not callable(getattr(adapter, key, None)) for key in required):
                raise ValueError('Complete reviewed adapter required')
            write = getattr(adapter, 'AUTHORIZED_TARGET_WRITES', False)
            csv = getattr(adapter, 'OWNS_NATIVE_CSV_TRANSPORT', False)
            if type(write) is not bool or type(csv) is not bool:
                raise ValueError('Explicit boolean adapter policies required')
            policies.add(write); csv_owners.add(csv)
            versions = getattr(adapter, 'FEEDBACK_VERSIONS', ())
            if not versions or any(not isinstance(v, str) or not v for v in versions):
                raise ValueError('Explicit feedback versions required')
            for version in versions:
                previous = self._feedback.get(version)
                # Shared schemas are allowed only with the same implementation;
                # choosing the first of two incompatible formatters is unsafe.
                if previous is not None and self._implementation(previous) is not self._implementation(adapter.feedback):
                    raise ValueError('Conflicting feedback implementations')
                self._feedback[version] = adapter.feedback
            rows = list(contracts)
            if not rows:
                raise ValueError('Each adapter needs bound source contracts')
            if not any(adapter is a for a in self._adapters):
                self._adapters.append(adapter)
            for row in rows:
                canonical = self._canonical(row)
                sid = canonical.get('source_task_id')
                if not isinstance(sid, str) or not sid or sid in self._sources:
                    raise ValueError('Distinct reviewed source identities required')
                if not adapter.enabled(canonical):
                    raise ValueError('Source does not belong to reviewed adapter')
                self._sources[sid] = (adapter, canonical)
        if not self._sources or len(policies) != 1 or len(csv_owners) != 1:
            raise ValueError('Bundle must have one write and transport policy')
        self.AUTHORIZED_TARGET_WRITES = policies.pop()
        self.OWNS_NATIVE_CSV_TRANSPORT = csv_owners.pop()
        self.FEEDBACK_VERSIONS = tuple(sorted(self._feedback))

    @staticmethod
    def _implementation(method):
        return getattr(method, '__func__', method)

    @staticmethod
    def _canonical(contract):
        if not isinstance(contract, dict):
            raise ValueError('Source contract must be an object')
        return deepcopy({k: v for k, v in contract.items() if k != 'admission_result'})

    def enabled(self, contract):
        # Capture malformed/unknown members of these families too, so they fail
        # binding instead of silently falling back to another execution path.
        return (contract.get('source_task_id') in self._sources
                or any(a.enabled(contract) for a in self._adapters))

    def _adapter(self, contract):
        canonical = self._canonical(contract)
        entry = self._sources.get(canonical.get('source_task_id'))
        if entry is None or canonical != entry[1]:
            raise ValueError('Task differs from its reviewed source contract')
        return entry[0]

    def require_admission(self, contract, proof):
        return self._adapter(contract).require_admission(contract, proof)

    def require_original_binding(self, contract, original, inventory):
        return self._adapter(contract).require_original_binding(contract, original, inventory)

    def NativeReadHooks(self, contract, proof, directory):
        return self._adapter(contract).NativeReadHooks(contract, proof, directory)

    def public_goal(self, contract):
        return self._adapter(contract).public_goal(contract)

    def fields(self, contract):
        return self._adapter(contract).fields(contract)

    def upload_files(self, contract, hooks):
        adapter = self._adapter(contract)
        supplier = getattr(adapter, 'upload_files', None)
        return supplier(contract, hooks) if supplier is not None else []

    def feedback(self, judgment):
        formatter = self._feedback.get(judgment.get('version'))
        if formatter is None:
            raise ValueError('Unregistered terminal feedback version')
        return formatter(judgment)

    def profile_for_contracts(self, contracts):
        rows = list(contracts)
        adapters = []
        for row in rows:
            adapter = self._adapter(row)
            if not any(adapter is a for a in adapters):
                adapters.append(adapter)
        profile = {}
        for adapter in adapters:
            hook = getattr(adapter, 'profile_for_contracts', None)
            if hook is None:
                continue
            # Keep family checks on the full manifest: passing only its own
            # subset could incorrectly permit incompatible environment mixing.
            value = hook(rows)
            if not isinstance(value, dict):
                raise ValueError('Invalid reviewed website profile')
            for key, item in value.items():
                if key in profile and profile[key] != item:
                    raise ValueError('Conflicting reviewed website profiles')
                profile[key] = deepcopy(item)
        return profile
