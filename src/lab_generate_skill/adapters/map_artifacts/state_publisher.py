"""Complete state through existing immutable files and mandatory original authority."""

import hashlib
import os
from pathlib import Path
import threading
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.domain.map_state_artifact import (
    MapStateArtifact,
    check_state_plan,
)
from lab_generate_skill.domain.map_private_artifact import (
    MapArtifactPlan,
    parse_map_artifact_plan,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.map_state_artifacts import MapStateArtifactPlans
from lab_generate_skill.ports.map_private_artifact import MapArtifactAuthority
from .writer import MapArtifactWriter


class MapStatePublisher:
    def __init__(
        self,
        workspace: Path,
        plans: MapStateArtifactPlans,
        authority: MapArtifactAuthority,
    ) -> None:
        if (
            not isinstance(workspace, Path)
            or not callable(getattr(authority, "verify", None))
            or not callable(getattr(plans, "plan", None))
        ):
            raise ValueError(
                "Explicit original workspace, plans and artifact authority required"
            )
        self.workspace, self.plans, self.authority = workspace, plans, authority
        self.owner = os.getpid(), threading.get_ident()
        self.attempts: set[str] = set()
        self.writers: list[MapArtifactWriter] = []
        self.results: list[MapStateArtifact] = []
        self.state = "ready"
        self.error: BaseException | None = None

    def publish(
        self,
        request: SiteTaskRequest,
        data: bytes,
        state_sha256: str,
        control: OperationControl,
    ) -> MapStateArtifact:
        request = SiteTaskRequest.model_validate(request)
        if (
            type(data) is not bytes
            or not data
            or type(state_sha256) is not str
            or len(state_sha256) != 64
            or any(c not in "0123456789abcdef" for c in state_sha256)
        ):
            raise ValueError(
                "Complete actual state bytes and original fingerprint required"
            )
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict(
                "Original Map state publisher worker/thread required"
            )
        if self.state != "ready" or request.operation.operation_id in self.attempts:
            raise InvalidTransition(
                "Map state publication stopped, active or already attempted"
            )
        control.checkpoint()
        self.attempts.add(request.operation.operation_id)
        self.state = "publishing"
        try:
            plan = parse_map_artifact_plan(self.plans.plan(request, control))
            check_state_plan(plan, request)
            if plan.workspace_root != str(self.workspace):
                raise OwnershipConflict("Map state plan changed original workspace")
            writer = MapArtifactWriter(plan, self.workspace, self.authority)
            self.writers.append(writer)
            writer.initialize(control)
            pin = writer.retain("state.json", data, control)
            if (pin.sha256, pin.size_bytes) != (
                hashlib.sha256(data).hexdigest(),
                len(data),
            ):
                raise OwnershipConflict("Complete native state retention changed bytes")
            handle = writer.seal(control)
            result = MapStateArtifact(
                plan=plan,
                handle=handle,
                file=pin,
                request_sha256=request.digest,
                state_sha256=state_sha256,
            )
            self.results.append(result)
            control.checkpoint()
            self.state = "ready"
            return result
        except BaseException as error:
            self.state, self.error = "failed", error
            raise
