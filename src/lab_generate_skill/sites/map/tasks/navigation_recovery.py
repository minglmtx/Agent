"""Concrete navigation task facts on the shared unchanged-state/Rails lifecycle."""

from typing import Literal, Self
from pydantic import model_validator
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.domain.map_state_artifact import (
    MapStateArtifact,
)
from lab_generate_skill.domain.map_frontend_lifecycle import (
    MapFrontendCleared,
    MapFrontendResumed,
)
from .navigation_admission import task_input
from .state_admission import snapshot_reference, check_native


class NavigationSnapshot(Contract):
    schema_version: Literal["map-navigation-snapshot/1"] = "map-navigation-snapshot/1"
    request: SiteTaskRequest
    native: MapStateArtifact

    @model_validator(mode="after")
    def original(self) -> Self:
        task_input(self.request)
        check_native(self.native, self.request)
        if self.request.action != "snapshot":
            raise ValueError("Original Map snapshot request required")
        return self


class NavigationObserved(Contract):
    schema_version: Literal["map-navigation-observed/1"] = "map-navigation-observed/1"
    request: SiteTaskRequest
    snapshot: NavigationSnapshot
    native: MapStateArtifact

    @model_validator(mode="after")
    def original(self) -> Self:
        snapshot_reference(
            self.request,
            self.snapshot.request,
            self.snapshot.model_dump_json().encode(),
            None,
            schema_version="map-navigation-snapshot/1",
        )
        check_native(self.native, self.request)
        if (
            self.request.action not in ("prepare", "inspect")
            or self.native.state_sha256 != self.snapshot.native.state_sha256
            or self.native.plan.scope != self.snapshot.native.plan.scope
            or self.native.plan.token != self.snapshot.native.plan.token
        ):
            raise ValueError("Original unchanged Map state required")
        return self


class NavigationRestored(Contract):
    schema_version: Literal["map-navigation-restored/1"] = "map-navigation-restored/1"
    request: SiteTaskRequest
    snapshot: NavigationSnapshot
    cleared: MapFrontendCleared

    @model_validator(mode="after")
    def original(self) -> Self:
        snapshot_reference(
            self.request,
            self.snapshot.request,
            self.snapshot.model_dump_json().encode(),
            None,
            schema_version="map-navigation-snapshot/1",
        )
        if (
            self.request.action != "restore"
            or self.cleared.spec.inputs.files.instance_id
            != self.snapshot.native.plan.token.expected_resource_id
        ):
            raise ValueError("Original Map restore/instance required")
        return self


class NavigationResumed(Contract):
    schema_version: Literal["map-navigation-resumed/1"] = "map-navigation-resumed/1"
    request: SiteResumeRequest
    restored: NavigationRestored
    resumed: MapFrontendResumed
    native: MapStateArtifact

    @model_validator(mode="after")
    def original(self) -> Self:
        original = self.restored.snapshot.native
        inspection = SiteTaskRequest.model_validate(
            {
                **self.request.restore_request.model_dump(),
                "operation": self.request.operation,
            }
        )
        check_native(self.native, inspection)
        if (
            self.request.restore_request != self.restored.request
            or self.resumed.cleared != self.restored.cleared
            or self.resumed.before_sha256 != original.state_sha256
            or self.native.state_sha256 != original.state_sha256
            or self.native.plan.scope != original.plan.scope
            or self.native.plan.token != original.plan.token
        ):
            raise ValueError("Complete Map resumed state lost its original recovery")
        return self
