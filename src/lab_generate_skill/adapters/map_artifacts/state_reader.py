"""Original request plan and full immutable state bytes; no native execution."""

import hashlib
from pathlib import Path
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.map_state_artifact import (
    MapStateArtifact,
    check_state_plan,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.map_private_artifact import MapArtifactAuthority
from lab_generate_skill.ports.map_state_artifacts import MapStateArtifactPlans
from .reader import MapArtifactReader


class OriginalMapStateReader:
    def __init__(
        self,
        workspace: Path,
        plans: MapStateArtifactPlans,
        authority: MapArtifactAuthority,
    ) -> None:
        if (
            not isinstance(workspace, Path)
            or not callable(getattr(plans, "plan", None))
            or not callable(getattr(authority, "verify", None))
        ):
            raise ValueError(
                "Explicit original workspace, plans and read authority required"
            )
        self.workspace, self.plans, self.authority = workspace, plans, authority

    def read(
        self,
        descriptor: MapStateArtifact,
        request: SiteTaskRequest,
        control: OperationControl,
    ) -> bytes:
        control.checkpoint()
        descriptor = MapStateArtifact.model_validate(descriptor)
        request = SiteTaskRequest.model_validate(request)
        check_state_plan(descriptor.plan, request)
        plan = self.plans.plan(request, control)
        if (
            plan != descriptor.plan
            or plan.workspace_root != str(self.workspace)
            or descriptor.request_sha256 != request.digest
        ):
            raise OwnershipConflict(
                "Map complete state changed original request/plan/workspace"
            )
        reader = MapArtifactReader(plan, self.workspace, self.authority)
        raw = reader.read(descriptor.handle, descriptor.file.path, control)
        if (len(raw), hashlib.sha256(raw).hexdigest()) != (
            descriptor.file.size_bytes,
            descriptor.file.sha256,
        ):
            raise EvidenceIntegrityError(
                "Map complete state descriptor differs from original file"
            )
        control.checkpoint()
        return raw
