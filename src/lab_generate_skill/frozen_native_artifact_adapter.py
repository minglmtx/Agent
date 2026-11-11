"""Bind a proven native artifact client to the ordinary actor session factory.

Only the trusted frozen bootstrap supplies the native binding function. Tasks
cannot select imports or tool implementations. Original source gates remain in
both hook construction and the native client binder; CPU bootstrap is unused.
"""
from contextlib import contextmanager
import json
from pathlib import Path

from .frozen_native_family_adapter import FrozenNativeFamilyAdapter


class FrozenNativeArtifactAdapter(FrozenNativeFamilyAdapter):
    def __init__(self, *, bind_client_session, **kwargs):
        if not callable(bind_client_session):
            raise ValueError('An original verified native client binder is required')
        # A frozen bootstrap can provide a longer-lived proof session. Otherwise
        # own one for this adapter/bridge: fully check once per current source,
        # then revalidate immutable proof and local file identities on reuse.
        from .native_proof_session import NativeProofSession
        self._owned_proof_session = kwargs.get('proof_session') is None
        if self._owned_proof_session:
            kwargs['proof_session'] = NativeProofSession()
        super().__init__(hook_protocol='private_reference_class', **kwargs)
        self.bind_client_session = bind_client_session
        self._pending = {}
        self._bound_contracts = []

    def NativeReadHooks(self, contract, descriptor, directory):
        source = self._verified_source(contract, descriptor)
        private = source['cycles'][0]['controls']['initial_no_op']['private_reference']
        current = self.canonical(contract)
        hooks = source['driver'].Hooks(current, private, directory, proof=source)
        self._pending[id(hooks)] = (hooks, source, current, Path(directory).resolve(), descriptor)
        return hooks

    def bind(self, base_factory, site, contract, directory, auth, hooks):
        record = self._pending.get(id(hooks))
        if record is None or record[0] is not hooks:
            raise ValueError('Actual admitted artifact hooks are required')
        _, source, current, expected_directory, descriptor = record
        if current != self.canonical(contract) or Path(directory).resolve() != expected_directory:
            raise ValueError('Artifact session differs from the admitted task or attempt')
        if getattr(hooks, 'site', None) is not site or getattr(hooks, 'prepared', False) is not True:
            raise ValueError('Actual native hooks must be prepared on this isolated site')
        # Recheck immutable source files after preparation, before enabling tools.
        # The proof session reuses the complete gate only while its inputs match.
        source = self._verified_source(contract, descriptor)
        packet = source['native_packet']
        result = self.bind_client_session(base_factory,
            artifact_root=Path(directory)/'client-live', site_origin=site.url,
            candidate_root=packet['candidate_root'],
            plan=json.loads(Path(packet['plan_path']).read_text()),
            driver_module=source['driver'], case=current,
            cycles=source['cycles'], directories=source['directories'],
            hooks=hooks, current_account_auth=auth)
        # One ordinary factory per admitted hook and isolated attempt.
        del self._pending[id(hooks)]
        self._bound_contracts.append(current)
        return result

    def has_bound_session(self, contract):
        return self.enabled(contract) and self.canonical(contract) in self._bound_contracts


@contextmanager
def session_bridge(runner, adapter):
    if not isinstance(adapter, FrozenNativeArtifactAdapter):
        raise ValueError('A trusted frozen native artifact adapter is required')
    original = runner.make_session
    if getattr(original, '_frozen_artifact_session_bridge', False):
        raise ValueError('An artifact session bridge is already installed')

    def make_session(site, contract, directory, auth, *args, **kwargs):
        base = original(site, contract, directory, auth, *args, **kwargs)
        if not adapter.enabled(contract):
            return base
        return adapter.bind(base, site, contract, directory, auth,
                            kwargs.get('native_read_hooks'))

    make_session._frozen_artifact_session_bridge = True
    runner.make_session = make_session
    try:
        yield
    finally:
        if runner.make_session is not make_session:
            raise ValueError('Another owner replaced the ordinary session factory')
        runner.make_session = original
        adapter._pending.clear()
        adapter._bound_contracts.clear()
        if adapter._owned_proof_session:
            adapter.proof_session.close()
