"""One explicit validation slot alongside its unchanged canonical parent.

Uses the existing atomic claim transaction and exact replay/unknown semantics.
There is no fallback from normal claims, deletion, release or ownership transfer.
The same trusted root/scope and original private task remain mandatory.
"""

from pathlib import Path
from lab_generate_skill.domain.claims import (
    SourceClaimBinding,
    SourceClaimKey,
    SourceClaimRecord,
    SourceClaimReceipt,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.source_stage_validation import SourceStageValidation
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.ports.source_stage_validation import (
    SourceStageValidationAuthority,
)
from lab_generate_skill.adapters.plans.claim_evidence import MAX_CLAIM_BYTES
from lab_generate_skill.adapters.storage.atomic_snapshot import AtomicSnapshotFile
from .claims import FileSourceClaims
from .stage_validation_snapshot import checked_validation_parent


class _ValidationAuthority:
    def __init__(
        self,
        root: Path,
        controls: OperationControls,
        validation: SourceStageValidation,
        authority: SourceStageValidationAuthority,
    ) -> None:
        self.root, self.controls = root, controls
        self.validation, self.authority = validation, authority

    def _parent(self, operation: OperationContext) -> None:
        control = self.controls.bind(operation)
        with checked_validation_parent(self.root, self.validation, control):
            self.authority.verify_parent(self.validation, operation)

    def authorize_create(
        self, binding: SourceClaimBinding, plan: RunPlan, op: OperationContext
    ) -> None:
        self.validation.require_current_binding(binding)
        self._parent(op)
        self.authority.authorize_current(self.validation, binding, plan, op)

    def verify_owner(self, record: SourceClaimRecord, op: OperationContext) -> None:
        self.validation.require_current_binding(record.binding)
        self._parent(op)
        self.authority.verify_current(self.validation, record, op)


class FileSourceStageValidations(FileSourceClaims):
    def __init__(
        self,
        root: Path,
        scope_id: str,
        controls: OperationControls,
        evidence: EvidenceStore,
        plans: RunPlans,
        authority: SourceStageValidationAuthority,
        *,
        validation: SourceStageValidation,
    ) -> None:
        validation = SourceStageValidation.model_validate(validation)
        if not isinstance(authority, SourceStageValidationAuthority) or not all(
            callable(getattr(authority, name, None))
            for name in ("verify_parent", "authorize_current", "verify_current")
        ):
            raise TypeError("Explicit live stage-validation authority required")
        if validation.parent.record.binding.scope_id != scope_id:
            raise OwnershipConflict("Validation cannot change trusted parent scope")
        self.validation = validation
        super().__init__(
            root,
            scope_id,
            controls,
            evidence,
            plans,
            _ValidationAuthority(root, controls, validation, authority),
        )

    def claim(
        self, binding: SourceClaimBinding, op: OperationContext
    ) -> SourceClaimReceipt:
        if self.validation.schema_version == "source-stage-validation/1":
            return super().claim(binding, op)
        # Serialize different targets of the SAME retained parent before taking
        # child -> canonical parent locks. Reads never acquire this outer lock.
        # This is an existing snapshot lock, not another claim/outcome ledger.
        file = AtomicSnapshotFile(
            self._root,
            self.validation.parent.reference.sha256 + ".stage-admission.json",
            max_bytes=MAX_CLAIM_BYTES,
        )
        with file.locked(self._controls.bind(op)):
            return super().claim(binding, op)

    def _file(self, key: SourceClaimKey) -> AtomicSnapshotFile:
        # Never derive a new scope from the caller or route arbitrary source IDs.
        if key != self.validation.parent.record.binding.key:
            raise OwnershipConflict("Validation key changed original source/scope")
        return AtomicSnapshotFile(
            self._root, self.validation.filename, max_bytes=MAX_CLAIM_BYTES
        )
