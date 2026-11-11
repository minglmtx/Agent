"""Exact storage launch inputs, selected by trusted deployment configuration.

Inline plan bytes break the bootstrap cycle: the store need not already exist
to resolve its own plan. A declaration does not prove publication or approval.
"""

import hashlib
from typing import Literal, Self
from pydantic import Field, model_validator
from .release_activation import ReleaseActivation, ReleaseDeployment
from .run_plan import RunPlan
from .storage_scope import StorageScope
from .validation import Contract


class StorageLaunch(Contract):
    schema_version: Literal["storage-launch/1"] = "storage-launch/1"
    scope: StorageScope
    plan: RunPlan
    deployment: ReleaseDeployment
    activation: ReleaseActivation
    revision: int = Field(ge=1, le=1024)

    @model_validator(mode="after")
    def frozen_inputs(self) -> Self:
        scope, plan = self.scope, self.plan
        plan.check_binding(scope.run)
        raw = plan.model_dump_json().encode()
        ref = scope.run.plan_ref
        if (
            ref.uri != "cas://sha256/" + ref.sha256
            or len(raw) != ref.size_bytes
            or hashlib.sha256(raw).hexdigest() != ref.sha256
        ):
            raise ValueError("Storage launch must carry the exact frozen RunPlan")
        if scope.claim is not None and scope.claim.task not in plan.tasks:
            raise ValueError("Storage source claim is absent from the complete plan")
        if (
            self.activation.release_id != scope.binding.release_id
            or self.activation.manifest_ref != scope.run.release_ref
            or self.revision > self.deployment.max_switches
        ):
            raise ValueError("Storage launch differs from selected publication")
        return self
