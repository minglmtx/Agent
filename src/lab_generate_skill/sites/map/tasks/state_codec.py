"""Concrete task evidence choices for the single native Map lifecycle."""

from typing import Literal
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.domain.map_state_artifact import MapStateArtifact
from lab_generate_skill.domain.map_frontend_lifecycle import (
    MapFrontendCleared,
    MapFrontendResumed,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from .overlay_admission import task_input as overlay_input
from .navigation_admission import task_input as navigation_input
from .overlay_spec import NativeOverlaySpec
from .navigation_spec import NavigationSpec
from .overlay_recovery import (
    OverlaySnapshot,
    OverlayObserved,
    OverlayRestored,
    OverlayResumed,
)
from .navigation_recovery import (
    NavigationSnapshot,
    NavigationObserved,
    NavigationRestored,
    NavigationResumed,
)

MapSnapshot = OverlaySnapshot | NavigationSnapshot
MapRestored = OverlayRestored | NavigationRestored


class MapTaskStateCodec:
    def __init__(self, task: TaskIdentity) -> None:
        self.task = TaskIdentity.model_validate(task)
        if (task.site, task.contract_version, task.split) != ("map", 1, "train"):
            raise ValueError("Explicit original train Map task codec required")
        self.snapshot_schema: Literal[
            "map-overlay-snapshot/1", "map-navigation-snapshot/1"
        ]
        self.snapshot_type: type[OverlaySnapshot] | type[NavigationSnapshot]
        self.observed_type: type[OverlayObserved] | type[NavigationObserved]
        self.private_type: type[NativeOverlaySpec] | type[NavigationSpec]
        self.restored_type: type[OverlayRestored] | type[NavigationRestored]
        self.resumed_type: type[OverlayResumed] | type[NavigationResumed]
        if task.family == "native_route_map_data":
            self.family = "native_route_map_data"
            self.snapshot_schema = "map-overlay-snapshot/1"
            self.collector = "map-overlay-state"
            self.snapshot_type, self.observed_type = OverlaySnapshot, OverlayObserved
            self.private_schema, self.private_type = (
                "map-native-overlay/1",
                NativeOverlaySpec,
            )
            self.restored_type, self.resumed_type = OverlayRestored, OverlayResumed
            self.recovery_component = "map-native-overlay"
        elif task.family == "navigation_page_identity":
            self.family = "navigation_page_identity"
            self.snapshot_schema = "map-navigation-snapshot/1"
            self.collector = "map-navigation-state"
            self.private_schema, self.private_type = (
                "map-navigation-spec/1",
                NavigationSpec,
            )
            self.restored_type, self.resumed_type = (
                NavigationRestored,
                NavigationResumed,
            )
            self.recovery_component = "map-native-navigation"
            self.snapshot_type, self.observed_type = (
                NavigationSnapshot,
                NavigationObserved,
            )
        else:
            raise ValueError("Unsupported Map task codec")

    def check_input(self, request: SiteTaskRequest) -> None:
        if request.task != self.task:
            raise OwnershipConflict("Map codec changed original configured task")
        if self.family == "native_route_map_data":
            overlay_input(request)
        else:
            navigation_input(request)

    def snapshot(
        self, request: SiteTaskRequest, native: MapStateArtifact
    ) -> MapSnapshot:
        self.check_input(request)
        if self.family == "native_route_map_data":
            return OverlaySnapshot(request=request, native=native)
        return NavigationSnapshot(request=request, native=native)

    def observed(
        self, request: SiteTaskRequest, snapshot: MapSnapshot, native: MapStateArtifact
    ) -> OverlayObserved | NavigationObserved:
        self.check_input(request)
        if (
            isinstance(snapshot, OverlaySnapshot)
            and self.family == "native_route_map_data"
        ):
            return OverlayObserved(request=request, snapshot=snapshot, native=native)
        if (
            isinstance(snapshot, NavigationSnapshot)
            and self.family == "navigation_page_identity"
        ):
            return NavigationObserved(request=request, snapshot=snapshot, native=native)
        raise OwnershipConflict("Map observed state changed concrete snapshot codec")

    def restored(
        self,
        request: SiteTaskRequest,
        snapshot: MapSnapshot,
        cleared: MapFrontendCleared,
    ) -> MapRestored:
        self.check_input(request)
        if (
            isinstance(snapshot, OverlaySnapshot)
            and self.family == "native_route_map_data"
        ):
            return OverlayRestored(request=request, snapshot=snapshot, cleared=cleared)
        if (
            isinstance(snapshot, NavigationSnapshot)
            and self.family == "navigation_page_identity"
        ):
            return NavigationRestored(
                request=request, snapshot=snapshot, cleared=cleared
            )
        raise OwnershipConflict("Map restored state changed concrete snapshot codec")

    def read_restored(self, raw: str) -> MapRestored:
        if self.family == "native_route_map_data":
            result: MapRestored = OverlayRestored.model_validate_json(raw)
        else:
            result = NavigationRestored.model_validate_json(raw)
        self.check_input(result.request)
        return result

    def resumed(
        self,
        request: SiteResumeRequest,
        restored: MapRestored,
        resumed: MapFrontendResumed,
        native: MapStateArtifact,
    ) -> OverlayResumed | NavigationResumed:
        self.check_input(request.restore_request)
        if (
            isinstance(restored, OverlayRestored)
            and self.family == "native_route_map_data"
        ):
            return OverlayResumed(
                request=request, restored=restored, resumed=resumed, native=native
            )
        if (
            isinstance(restored, NavigationRestored)
            and self.family == "navigation_page_identity"
        ):
            return NavigationResumed(
                request=request, restored=restored, resumed=resumed, native=native
            )
        raise OwnershipConflict("Map resumed state changed concrete restoration codec")
