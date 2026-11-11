"""Selected read-only reference in the original task lifecycle, never a second RPC."""

from collections.abc import Callable
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.domain.map_database_artifact import MapDatabaseArtifact
from lab_generate_skill.domain.map_reference_selection import MapReferenceSelection
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from ..reference_selection import read_reference_selection
from .state_lifecycle import MapTaskLifecycle
from .state_admission import snapshot_reference


class MapReferenceDispatch:
    def __init__(
        self,
        lifecycle: MapTaskLifecycle,
        reader: EvidenceReader,
        publish: Callable[
            [SiteCaptureRequest, MapReferenceSelection, OperationControl],
            MapDatabaseArtifact,
        ],
    ) -> None:
        if lifecycle.codecs.family != "native_route_map_data":
            raise ValueError("MapData reference dispatcher cannot dispatch navigation")
        self.lifecycle, self.reader, self.publish = lifecycle, reader, publish
        self.attempted: set[tuple[str, int]] = set()
        self.result: SiteTaskResult | None = None

    def capture_task(
        self, request: SiteCaptureRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        request = SiteCaptureRequest.model_validate(request)
        if (request.collector_id, request.collector_version) != (
            "map-native-reference",
            "1",
        ) or request.selection_ref is None:
            raise ValueError("Explicit selected Map native reference required")
        task, inspection = self.lifecycle, request.inspection
        task._available(inspection.operation.operation_id)
        if (
            task.phase != "prepared"
            or task.snapshot is None
            or task.preparation is None
        ):
            raise InvalidTransition("Map reference requires original prepared task")
        snapshot_reference(
            inspection,
            task.snapshot.request,
            task.snapshot.model_dump_json().encode(),
            task.snapshot_ref,
            schema_version="map-overlay-snapshot/1",
        )
        selected = read_reference_selection(
            self.reader, request.selection_ref, inspection, control
        )
        if selected.original_request_key in self.attempted:
            raise InvalidTransition(
                "Original terminal request already dispatched; reuse its original evidence"
            )
        control.checkpoint()
        self.attempted.add(selected.original_request_key)
        task.operations.add(inspection.operation.operation_id)
        task.busy = True
        self.result = None
        try:
            native = MapDatabaseArtifact.model_validate(
                self.publish(request, selected, control)
            )
            if native.request != request or native.selected != selected:
                raise OwnershipConflict("Native DB publisher changed selected capture")
            self.result = SiteTaskResult(
                request_sha256=request.digest, private_result=native.model_dump_json()
            )
            control.checkpoint()
            return self.result
        except BaseException as error:
            task.phase, task.error = "quarantined", error
            task.retain_failure(error)
            setattr(error, "map_reference_result", self.result)
            raise
        finally:
            task.busy = False
