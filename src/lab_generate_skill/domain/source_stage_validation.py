"""Explicit corrected-stage validation, distinct from the immutable parent claim.

Neither construction, different run IDs nor a changed authorization reference
create another slot for the same parent/source and selected release.
"""

import hashlib
from typing import Literal, Self
from pydantic import model_validator
from .claims import SourceClaimReceipt, SourceClaimBinding
from .evidence import EvidenceRef
from .errors import OwnershipConflict
from .state_scope import private_state_ref
from .validation import Contract


class SourceStageValidation(Contract):
    schema_version: Literal[
        "source-stage-validation/1", "source-stage-validation/2"
    ] = "source-stage-validation/1"
    parent: SourceClaimReceipt
    target_release_ref: EvidenceRef
    authorization_ref: EvidenceRef
    stage_scope: Literal["corrected_actor_to_close"] = "corrected_actor_to_close"

    @model_validator(mode="after")
    def exact_parent_and_change(self) -> Self:
        private_state_ref(self.target_release_ref, "release-manifest/1")
        schema = self.authorization_ref.content_schema
        if schema not in (
            "task-stage-validation-authorization/1",
            "task-stage-validation-authorization/2",
            "task-stage-validation-authorization/3",
            "task-stage-validation-authorization/4",
        ) or (
            self.schema_version == "source-stage-validation/1"
            and schema != "task-stage-validation-authorization/1"
        ):
            raise ValueError("Unsupported exact stage authorization version")
        private_state_ref(self.authorization_ref, schema)
        if (
            self.target_release_ref.sha256
            == self.parent.record.binding.run.release_ref.sha256
        ):
            raise ValueError("A corrected-stage validation requires a changed release")
        return self

    @property
    def filename(self) -> str:
        if self.schema_version == "source-stage-validation/2":
            # The existing parent-level claim lock serializes target slots.
            # Different target histories stay visible for explicit outcome
            # review, including unknown commits; no release-wide permanent cap.
            target = self.target_release_ref.sha256.translate(
                str.maketrans("0123456789", "ghijklmnop")
            )
            return self.parent_prefix + target + ".json"
        # The canonical parent remains at parent.binding.key.filename.
        # Authorization/run/job/submission IDs cannot mint another validation.
        identity = ":".join(
            (
                self.parent.record.binding.key.filename,
                self.parent.reference.sha256,
                self.target_release_ref.sha256,
                self.stage_scope,
            )
        )
        digest = hashlib.sha256(identity.encode()).hexdigest()
        return digest + ".stage-validation-claim.json"

    @property
    def parent_prefix(self) -> str:
        identity = ":".join((self.parent.reference.sha256, self.stage_scope))
        return hashlib.sha256(identity.encode()).hexdigest() + ".stage-validation-"

    def require_current_binding(self, binding: SourceClaimBinding) -> None:
        binding = SourceClaimBinding.model_validate(binding)
        parent = self.parent.record.binding
        if (
            binding.scope_id != parent.scope_id
            or binding.task != parent.task
            or binding.run.release_ref != self.target_release_ref
            or binding.run.owner.run_id == parent.run.owner.run_id
            or binding.run.owner.job_id == parent.run.owner.job_id
            or binding.run.owner == parent.run.owner
        ):
            raise OwnershipConflict(
                "Validation requires the exact parent task/scope and a fresh current owner/release"
            )
