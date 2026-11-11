"""Complete native state file reference, distinct from an unchanged/reset verdict."""

from typing import Literal, Self
from pydantic import model_validator
from .validation import Contract, Sha256
from .map_private_artifact import MapArtifactPlan, MapArtifactHandle
from .release import ReleaseFile
from .site_task import SiteTaskRequest


def check_state_plan(plan: MapArtifactPlan, request: SiteTaskRequest) -> None:
    scope, token, op = plan.scope, plan.token, request.operation
    if (
        plan.producer != "native_database"
        or scope.task != request.task
        or (scope.owner.run_id, scope.owner.owner_id, scope.attempt_id)
        != (op.run_id, op.owner_id, op.attempt_id)
        or token.allocation_id != op.allocation_id
    ):
        raise ValueError("Complete Map state artifact changed original task/resource")


class MapStateArtifact(Contract):
    schema_version: Literal["map-state-artifact/1"] = "map-state-artifact/1"
    plan: MapArtifactPlan
    handle: MapArtifactHandle
    file: ReleaseFile
    request_sha256: Sha256
    state_sha256: Sha256

    @model_validator(mode="after")
    def complete_file(self) -> Self:
        if (
            self.plan.producer != "native_database"
            or self.handle.plan_sha256 != self.plan.digest
            or self.file.path != "state.json"
            or self.file.executable
            or not 0 < self.file.size_bytes <= self.plan.max_file_bytes
        ):
            raise ValueError("Original complete private native state file required")
        return self
