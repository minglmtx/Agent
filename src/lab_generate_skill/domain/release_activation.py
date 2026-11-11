"""Explicit deployment and activation proposals, never self-issued permission."""

from typing import Literal, Self
from pydantic import Field, model_validator
from .evidence import EvidenceRef
from .lifecycle import OperationContext
from .state_scope import private_state_ref
from .validation import Contract, Identifier


class ReleaseDeployment(Contract):
    schema_version: Literal["release-deployment/1"] = "release-deployment/1"
    deployment_id: Identifier
    max_switches: int = Field(ge=1, le=1024)


class ReleaseActivation(Contract):
    """Exact candidate and acceptance identity; authority must read/verify them."""

    schema_version: Literal["release-activation/1"] = "release-activation/1"
    release_id: Identifier
    manifest_ref: EvidenceRef
    registry_ref: EvidenceRef
    acceptance_ref: EvidenceRef

    @model_validator(mode="after")
    def private_references(self) -> Self:
        for ref, schema in (
            (self.manifest_ref, "release-manifest/1"),
            (self.registry_ref, "task-registry/1"),
            (self.acceptance_ref, "release-acceptance/1"),
        ):
            private_state_ref(ref, schema)
        return self


def check_publication_operation(op: OperationContext) -> None:
    if (
        op.mode != "execute"
        or op.parent_operation_id is not None
        or op.attempt_id is not None
        or op.allocation_id is not None
        or op.recovery_ref is not None
    ):
        raise ValueError(
            "Publication requires an independent run-level execute operation"
        )


class ReleaseSwitch(Contract):
    schema_version: Literal["release-switch/1"] = "release-switch/1"
    expected_revision: int = Field(ge=0, le=1023)
    activation: ReleaseActivation
    operation: OperationContext

    @model_validator(mode="after")
    def publication_operation(self) -> Self:
        check_publication_operation(self.operation)
        return self
