"""Frozen storage scope selected by trusted bootstrap, never self-authorization.

Names and paths are declarations. Runtime admission independently observes the
original controller and reads the original source claim before activation.
"""

from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import Field, model_validator
from .claims import SourceClaimBinding
from .errors import OwnershipConflict
from .lifecycle import OperationContext, ResourceOwner
from .evidence_sessions import EvidenceSessionBinding
from .evidence_storage import EvidenceStorageConfig
from .execution import RunBinding
from .process_identity import ProcessIdentity
from .scheduler import SlurmExecutionIdentity
from .state_scope import private_state_ref
from .validation import Contract


class StorageScope(Contract):
    schema_version: Literal["storage-scope/1"] = "storage-scope/1"
    binding: EvidenceSessionBinding
    config: EvidenceStorageConfig
    run: RunBinding
    writer: ProcessIdentity
    execution: SlurmExecutionIdentity
    workspace_root: str = Field(min_length=1, max_length=4096)
    claim: SourceClaimBinding | None

    @model_validator(mode="after")
    def exact_scope(self) -> Self:
        binding, config, run = self.binding, self.config, self.run
        private_state_ref(run.plan_ref, "run-plan/3")
        if (
            binding.owner != run.owner
            or binding.storage_id != config.storage_id
            or binding.storage_config_sha256 != config.sha256
            or binding.release_id != config.installation.manifest.release_id
            or run.release_ref != config.installation.manifest_ref
            or self.execution.job_id != self.execution.raw_job_id
            or run.owner.job_id != self.execution.job_id
        ):
            raise ValueError("Storage scope must retain exact run/config/release/job")
        require_storage_location(config, self.workspace_root)
        if binding.scope == "source":
            if (
                self.claim is None
                or self.claim.run != run
                or self.claim.task.identity.source_task_id != binding.source_task_id
            ):
                raise ValueError("Source storage requires its complete original claim")
        elif self.claim is not None:
            raise ValueError("Run storage cannot inherit a source claim")
        return self


class OwnerMetadataStorageScope(Contract):
    """Original private metadata before a task's source/RunPlan can be frozen.

    Source qualification must first persist its actual measurement/closure, so
    it cannot require a RunPlan that references the resulting context. This
    explicit storage-only scope never substitutes for StorageScope, a source
    claim or dispatch admission. Its namespace is the same existing run key.
    """

    schema_version: Literal["owner-metadata-storage-scope/1"] = (
        "owner-metadata-storage-scope/1"
    )
    binding: EvidenceSessionBinding
    config: EvidenceStorageConfig
    writer: ProcessIdentity
    execution: SlurmExecutionIdentity
    workspace_root: str = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def original_private_owner(self) -> Self:
        b, c = self.binding, self.config
        if (
            b.scope != "run"
            or b.source_task_id is not None
            or b.storage_id != c.storage_id
            or b.storage_config_sha256 != c.sha256
            or b.release_id != c.installation.manifest.release_id
            or self.execution.job_id != self.execution.raw_job_id
            or b.owner.job_id != self.execution.job_id
        ):
            raise ValueError(
                "Owner metadata must retain exact run namespace/config/release/job"
            )
        require_storage_location(c, self.workspace_root)
        return self


def require_storage_location(
    config: EvidenceStorageConfig, workspace_root: str
) -> None:
    """Same canonical location rules for both explicit metadata scope variants."""
    root = PurePosixPath(workspace_root)
    if (
        not root.is_absolute()
        or str(root) != workspace_root
        or root == PurePosixPath("/")
        or ".." in root.parts
        or "\0" in workspace_root
        or "\\" in workspace_root
    ):
        raise ValueError("Trusted workspace must be canonical and non-root")
    if not PurePosixPath(config.installation.workspace_root).is_relative_to(root):
        raise ValueError("Installation must belong to the trusted workspace")
    for value in (config.evidence_root, config.session_root):
        path = PurePosixPath(value)
        if path == root or not path.is_relative_to(root):
            raise ValueError("Storage roots must be below the trusted workspace")


def check_storage_scope_operation(
    scope: StorageScope, operation: OperationContext
) -> OperationContext:
    """Storage control is private run-level metadata, not an attempt permission."""
    return check_private_storage_operation(scope.run.owner, operation)


def check_private_storage_operation(
    owner: ResourceOwner, operation: OperationContext
) -> OperationContext:
    """Common physical-I/O scope for an explicitly admitted run owner."""
    owner = ResourceOwner.model_validate(owner)
    operation = OperationContext.model_validate(operation)
    if (
        (operation.run_id, operation.owner_id) != (owner.run_id, owner.owner_id)
        or operation.mode != "execute"
        or operation.parent_operation_id is not None
        or operation.attempt_id is not None
        or operation.allocation_id is not None
        or operation.recovery_ref is not None
        or operation.cancellation_ref is not None
    ):
        raise OwnershipConflict("Storage requires its private run-level operation")
    return operation
