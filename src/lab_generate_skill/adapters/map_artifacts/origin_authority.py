"""Parent-side original qualified context read before any Map worker effects."""

from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.public_context import PublicContextReceipt
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.task_phase_source import TaskPhaseSourceState
from lab_generate_skill.ports.task_phase_source import (
    TaskOriginSourceProof,
    TaskOriginContextSourceProof,
)
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.ports.contexts import ContextRecords
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.evidence_bytes import (
    require_complete_bytes,
    require_complete_read_bound,
)


class OriginalMapOriginAuthority:
    def __init__(
        self,
        *,
        contexts: ContextRecords | None,
        evidence: EvidenceReader | None,
        source: TaskOriginSourceProof | None,
        read_operation: OperationContext | None,
    ) -> None:
        self.contexts, self.evidence = contexts, evidence
        if source is not None and not callable(getattr(source, "verify_source", None)):
            raise ValueError("Original task source proof required")
        self.source = source
        self.read_operation = (
            None
            if read_operation is None
            else OperationContext.model_validate(read_operation)
        )

    def verify_origin(
        self,
        spec: SiteResourceSpec,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        spec = SiteResourceSpec.model_validate(spec)
        spec.check_operation(operation, "execute")
        cfg, inputs = spec.configuration, spec.configuration.map_inputs
        if not isinstance(inputs, MapNavigationWorkerInputs):
            raise OwnershipConflict("Selected navigation origin authority only")
        control.checkpoint()
        origin = inputs.origin
        if origin.mode == "dynamic":
            return
        if (
            self.contexts is None
            or self.evidence is None
            or self.source is None
            or self.read_operation is None
        ):
            raise OwnershipConflict(
                "Frozen origin requires original task source, qualified ContextRecords and complete evidence"
            )
        read = self.read_operation
        if (
            read.run_id,
            read.owner_id,
            read.attempt_id,
            read.allocation_id,
            read.recovery_ref,
            read.mode,
        ) != (
            cfg.token.owner.run_id,
            cfg.token.owner.owner_id,
            None,
            None,
            None,
            "execute",
        ):
            raise OwnershipConflict(
                "Origin source read changed original independent run scope"
            )
        qualified_scope = None
        if isinstance(self.source, TaskOriginContextSourceProof):
            verified, original_scope = self.source.verify_source_context(read)
            qualified_scope = StateScope.model_validate(original_scope)
        else:
            verified = self.source.verify_source(read)
        progress = TaskPhaseSourceState.model_validate(verified)
        pending = progress.intent
        if (
            progress.intent.binding.run.owner != cfg.token.owner
            or progress.task.identity != inputs.scope.task
            or progress.task.private_spec_ref.sha256 != inputs.private_input_sha256
            or progress.public_context_ref != origin.source_context_ref
            or progress.context_receipt_ref != origin.source_context_receipt_ref
            or pending is None
            or pending.binding.run != progress.intent.binding.run
            or pending.binding.task != inputs.scope.task
            or pending.binding.attempt_id != inputs.scope.attempt_id
            or pending.public_context_ref != progress.public_context_ref
        ):
            raise OwnershipConflict(
                "Origin differs from original pending construction/private context"
            )
        control.checkpoint()
        assert (
            origin.source_context_receipt_ref is not None
            and origin.source_context_ref is not None
        )
        receipt = PublicContextReceipt.model_validate(
            self.contexts.load_context(origin.source_context_receipt_ref, operation)
        )
        if (
            (receipt.scope.owner, receipt.scope.task, receipt.public_context_ref)
            != (
                cfg.token.owner if qualified_scope is None else qualified_scope.owner,
                inputs.scope.task,
                origin.source_context_ref,
            )
            or receipt.scope.attempt_id == inputs.scope.attempt_id
            or (qualified_scope is not None and receipt.scope != qualified_scope)
        ):
            raise OwnershipConflict(
                "Origin changed original source scope/context or reused attempt"
            )
        require_complete_read_bound(origin.source_context_ref, 2 * 1024**2)
        raw = self.evidence.read(origin.source_context_ref, control=control)
        require_complete_bytes(origin.source_context_ref, raw)
        public = PublicConstructionContext.model_validate_json(raw)
        if (
            public.context_id != receipt.scope.context_id
            or public.task.identity != inputs.scope.task
            or public.task.start_url != origin.source_start_url
        ):
            raise OwnershipConflict(
                "Origin differs from exact original public source bytes"
            )
        control.checkpoint()
