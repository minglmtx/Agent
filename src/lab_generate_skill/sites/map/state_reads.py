"""Complete original preparation facts shared by selected Map checks."""

import hashlib
from typing import TypeVar
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.map_state_artifact import MapStateArtifact
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.map_state_artifacts import MapStateFileReader
from lab_generate_skill.ports.lifecycle import OperationControl
from .state_fact import CompleteMapState, complete_state
from .tasks.overlay_recovery import OverlaySnapshot, OverlayObserved
from .tasks.navigation_recovery import NavigationSnapshot, NavigationObserved
from .tasks.state_codec import MapTaskStateCodec
from .tasks.state_admission import check_native

T = TypeVar("T", bound=Contract)


class MapStateReads:
    def __init__(self, store: EvidenceReader, files: MapStateFileReader) -> None:
        self.store, self.files = store, files

    def read(
        self, ref: EvidenceRef, schema: str, model: type[T], control: OperationControl
    ) -> T:
        private_state_ref(ref, schema)
        if ref.media_type != "application/json":
            raise ValueError("Private original Map JSON record required")
        raw = self.store.read(ref, control=control)
        if (len(raw), hashlib.sha256(raw).hexdigest()) != (ref.size_bytes, ref.sha256):
            raise EvidenceIntegrityError("Original Map CAS bytes changed")
        result = model.model_validate_json(raw)
        if result.model_dump_json().encode() != raw:
            raise EvidenceIntegrityError("Noncanonical original Map CAS record")
        control.checkpoint()
        return result

    def native(
        self,
        descriptor: MapStateArtifact,
        request: SiteTaskRequest,
        control: OperationControl,
    ) -> CompleteMapState:
        check_native(descriptor, request)
        raw = self.files.read(descriptor, request, control)
        if (len(raw), hashlib.sha256(raw).hexdigest()) != (
            descriptor.file.size_bytes,
            descriptor.file.sha256,
        ):
            raise EvidenceIntegrityError("Complete original Map native bytes changed")
        state = complete_state(raw, descriptor, request)
        control.checkpoint()
        return state

    def prepared(
        self,
        result: SiteTaskResult,
        request: SiteTaskRequest,
        control: OperationControl,
    ) -> OverlayObserved | NavigationObserved:
        if (
            request.action != "prepare"
            or request.snapshot_ref is None
            or result.request_sha256 != request.digest
        ):
            raise OwnershipConflict("Original Map prepare result and snapshot required")
        codec = MapTaskStateCodec(request.task)
        codec.check_input(request)
        observed = codec.observed_type.model_validate_json(result.private_result)
        snapshot = self.read(
            request.snapshot_ref, codec.snapshot_schema, codec.snapshot_type, control
        )
        if (
            observed.request != request
            or observed.snapshot != snapshot
            or observed.model_dump_json() != result.private_result
        ):
            raise OwnershipConflict(
                "Map preparation changed original persisted measurement"
            )
        before = self.native(snapshot.native, snapshot.request, control)
        current = self.native(observed.native, request, control)
        if before.sha256 != current.sha256:
            raise OwnershipConflict(
                "Complete Map preparation changed original persistent state"
            )
        return observed
