"""Existing source claims through a fixed child, followed by explicit entitlement.

The mandatory business authority is separate from child read delegation. Its
callback still needs its own bounded production implementation; a file or scope
alone never grants business permission. No old ledger fallback is provided.
"""

from pathlib import Path
from lab_generate_skill.domain.claims import SourceClaimKey, SourceClaimRecord
from lab_generate_skill.domain.source_stage_validation import SourceStageValidation
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.storage_scope import (
    StorageScope,
    check_storage_scope_operation,
)
from lab_generate_skill.ports.claims import ClaimAuthority
from lab_generate_skill.ports.lifecycle import OperationControls, OperationControl
from lab_generate_skill.adapters.processes.combined_control import CombinedControl
from .claim_protocol import (
    ClaimReadCommand,
    ClaimReadRequest,
    StageValidationClaimReadCommand,
    check_claim_root,
)
from .claim_transport import ClaimReadTransport, ClaimReadExecution


class StorageClaimReader:
    def __init__(
        self,
        root: Path,
        scope: StorageScope,
        controls: OperationControls,
        authority: ClaimAuthority,
        *,
        validation: SourceStageValidation | None = None,
    ) -> None:
        scope = StorageScope.model_validate(scope)
        if not isinstance(root, Path) or scope.claim is None:
            raise ValueError("Claim reader requires a Path and complete source scope")
        check_claim_root(str(root), scope)
        self._validation = (
            None
            if validation is None
            else SourceStageValidation.model_validate(validation)
        )
        if self._validation is not None:
            self._validation.require_current_binding(scope.claim)
        self._root, self._scope, self._controls, self._authority = (
            root,
            scope,
            controls,
            authority,
        )
        self._transport = ClaimReadTransport()
        self._last: ClaimReadExecution | None = None

    @property
    def last_execution(self) -> ClaimReadExecution | None:
        """Last read confirmed by BOTH child transport and explicit authority."""
        return self._last

    def read(
        self, key: SourceClaimKey, op: OperationContext, *, control: OperationControl
    ) -> SourceClaimRecord:
        op = check_storage_scope_operation(self._scope, op)
        supervised = CombinedControl(control, self._controls.bind(op))
        supervised.checkpoint()
        assert self._scope.claim is not None
        if SourceClaimKey.model_validate(key) != self._scope.claim.key:
            raise OwnershipConflict("Claim key differs from original storage scope")
        command: ClaimReadRequest
        if self._validation is None:
            command = ClaimReadCommand(
                scope=self._scope, root=str(self._root), operation=op
            )
        else:
            command = StageValidationClaimReadCommand(
                scope=self._scope,
                root=str(self._root),
                operation=op,
                validation=self._validation,
            )
        result = self._transport.execute(command, supervised)
        assert result.reply.record is not None
        try:
            supervised.checkpoint()
            self._authority.verify_owner(result.reply.record, op)
            supervised.checkpoint()
        except BaseException as error:
            error.claim_read = result  # type: ignore[attr-defined]
            raise
        self._last = result
        return result.reply.record
