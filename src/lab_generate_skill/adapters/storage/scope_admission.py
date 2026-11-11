"""Pin storage rights to a trusted scope and an observed live Slurm controller.

Activation reads a source claim once, before this store is used. Claims are
immutable; rereading them from each I/O callback would recurse into control-plane
storage. No plan/CAS/current lookup occurs inside authorization. This capability
does not approve a release, grant model/task dispatch, or survive controller exit.
"""

from threading import Lock
from lab_generate_skill.domain.claims import SourceClaimRecord
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.domain.evidence_sessions import (
    EvidenceSessionBinding,
    check_evidence_cleanup,
)
from lab_generate_skill.domain.evidence_storage import EvidenceStorageConfig
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.storage_scope import (
    StorageScope,
    OwnerMetadataStorageScope,
    check_storage_scope_operation,
    check_private_storage_operation,
)
from lab_generate_skill.domain.storage_termination import StorageProcessEnd
from lab_generate_skill.ports.claims import SourceClaimReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.slurm.linux_cgroups import (
    KernelCgroupObservation,
    observe_current_cgroup,
)


class PinnedSlurmStorageAdmission:
    def __init__(self, scope: StorageScope | OwnerMetadataStorageScope) -> None:
        # An explicit typed metadata scope is required; malformed old run/source
        # inputs cannot downgrade to pre-claim metadata permission.
        self._scope = (
            OwnerMetadataStorageScope.model_validate(scope)
            if isinstance(scope, OwnerMetadataStorageScope)
            else StorageScope.model_validate(scope)
        )
        self._lock = Lock()
        self._started = False
        self._active = False
        self._stopped = False
        self._accepted: dict[str, OperationContext] = {}
        self._source_record: SourceClaimRecord | None = None
        self._activation: KernelCgroupObservation | None = None
        self._last: KernelCgroupObservation | None = None

    @property
    def source_record(self) -> SourceClaimRecord | None:
        return self._source_record

    @property
    def activation_observation(self) -> KernelCgroupObservation | None:
        return self._activation

    @property
    def last_observation(self) -> KernelCgroupObservation | None:
        return self._last

    def _writer(self, control: OperationControl) -> None:
        control.checkpoint()
        if current_process_identity() != self._scope.writer:
            raise OwnershipConflict("Storage capability belongs to another controller")
        control.checkpoint()

    def _operation(self, operation: OperationContext) -> OperationContext:
        if isinstance(self._scope, OwnerMetadataStorageScope):
            return check_private_storage_operation(self._scope.binding.owner, operation)
        return check_storage_scope_operation(self._scope, operation)

    def _binding(
        self, binding: EvidenceSessionBinding, config: EvidenceStorageConfig
    ) -> None:
        if (
            EvidenceSessionBinding.model_validate(binding) != self._scope.binding
            or EvidenceStorageConfig.model_validate(config) != self._scope.config
        ):
            raise OwnershipConflict(
                "Storage binding/config differs from admitted scope"
            )

    def activate(
        self,
        claims: SourceClaimReader | None,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        """Once-only activation; any failed attempt requires a new explicit assembly."""
        with self._lock:
            if self._started or self._stopped:
                raise InvalidTransition("Storage admission activation is once-only")
            self._started = True
        operation = self._operation(operation)
        scope = self._scope
        claim = scope.claim if isinstance(scope, StorageScope) else None
        if (claim is None) != (claims is None):
            raise OwnershipConflict("Only source storage requires existing claims")
        self._writer(control)
        before = observe_current_cgroup(scope.execution, scope.writer, control)
        record = None
        if claim is not None and claims is not None:
            record = SourceClaimRecord.model_validate(
                claims.read(claim.key, operation, control=control)
            )
            if record.binding != claim:
                raise OwnershipConflict("Persistent claim differs from storage source")
        self._writer(control)
        after = observe_current_cgroup(scope.execution, scope.writer, control)
        if before.membership != after.membership:
            raise OwnershipConflict(
                "Storage controller membership changed at activation"
            )
        with self._lock:
            if self._stopped:
                raise InvalidTransition("Storage admission stopped during activation")
            self._source_record, self._activation, self._last = record, before, after
            self._active = True

    def stop_new_io(self) -> None:
        """Idempotently revoke future admissions; original cleanup stays available."""
        with self._lock:
            self._stopped = True

    def authorize_storage(
        self,
        binding: EvidenceSessionBinding,
        config: EvidenceStorageConfig,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self._binding(binding, config)
        operation = self._operation(operation)
        with self._lock:
            self._require_active()
        self._writer(control)
        observed = observe_current_cgroup(
            self._scope.execution, self._scope.writer, control
        )
        control.checkpoint()
        with self._lock:
            self._require_active()
            assert self._activation is not None
            self._last = observed
            if observed.membership != self._activation.membership:
                raise OwnershipConflict(
                    "Storage controller left its original Slurm scope"
                )
            if operation.operation_id in self._accepted:
                raise InvalidTransition("Storage operation was already admitted")
            self._accepted[operation.operation_id] = operation

    def _require_active(self) -> None:
        if not self._active or self._stopped:
            raise InvalidTransition("Storage admission is inactive or stopped")

    def authorize_cleanup(
        self,
        binding: EvidenceSessionBinding,
        config: EvidenceStorageConfig,
        original: OperationContext,
        cleanup: OperationContext,
        ending: StorageProcessEnd | None,
        control: OperationControl,
    ) -> None:
        self._binding(binding, config)
        original = self._operation(original)
        cleanup = OperationContext.model_validate(cleanup)
        check_evidence_cleanup(original, cleanup)
        if cleanup.cancellation_ref is not None:
            raise OwnershipConflict(
                "Storage cleanup needs independent uncancelled scope"
            )
        self._writer(control)
        with self._lock:
            if self._accepted.get(original.operation_id) != original:
                raise OwnershipConflict("Cleanup has no exact original admission")
        if ending is not None:
            ending = StorageProcessEnd.model_validate(ending)
            if ending.controller != self._scope.writer:
                raise OwnershipConflict("Storage ending belongs to another controller")
        # Reap provenance, request binding and worker death are independently
        # checked by the original transport and fixed resolver. None is isolation.
        control.checkpoint()
