"""Real Map state files plus explicitly synthetic site/native/kernel rights."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from lab_generate_skill.adapters.map_artifacts.state_input_transport import (
    MapStateInputsTransport,
)
from lab_generate_skill.adapters.map_artifacts.state_graph_checks import (
    MapStateGraphChecks,
)
from lab_generate_skill.bootstrap.map_state_qualification import (
    map_state_qualifications,
)
from lab_generate_skill.bootstrap.deferred_state_records import (
    DeferredStateQualificationChecks,
)
from lab_generate_skill.sites.map.tasks.overlay_state_checks import OverlayStateChecks
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.map_state_artifact import MapStateArtifact
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.ports.lifecycle import OperationControl
from state_read_fixtures import StateReadCase, reader_case
from installed_source_fixtures import InstalledFixture


@dataclass
class MapInputsCase:
    metadata: StateReadCase
    inputs: MapStateInputsTransport
    checks: MapStateGraphChecks
    original: OverlayStateChecks


def input_case(
    root: Path, qualified: Any, installed: InstalledFixture
) -> MapInputsCase:
    c = qualified.original
    c.observer = "controller"
    original = qualified.qualifications.checks.original()
    assert isinstance(original, OverlayStateChecks)
    metadata = reader_case(
        root, c.resource.evidence._blobs.parent, c.scope.task, installed
    )
    inputs = MapStateInputsTransport(
        metadata.scope, metadata.current.store, metadata.current.admission, c.scope.task
    )
    binding = map_state_qualifications(
        c.resource.evidence,
        c.resource.controls,
        qualified.authority,
        c.resource.spec,
        qualified.live.site,
        state_inputs=inputs,
    )
    deferred = binding.checks
    assert isinstance(deferred, DeferredStateQualificationChecks)
    checks = deferred.original()
    assert isinstance(checks, MapStateGraphChecks)
    return MapInputsCase(metadata, inputs, checks, original)


class CountNativeFiles:
    def __init__(self, original: Any) -> None:
        self.original = original
        self.calls: list[tuple[MapStateArtifact, SiteTaskRequest]] = []

    def read(
        self,
        artifact: MapStateArtifact,
        request: SiteTaskRequest,
        control: OperationControl,
    ) -> bytes:
        self.calls.append((artifact, request))
        raw = self.original.read(artifact, request, control)
        if type(raw) is not bytes:
            raise TypeError("Original Map native file reader must return bytes")
        return raw


def append_external_resolved_history(path: Path) -> None:
    """A valid changed fixture history, never an original runtime write/grant."""
    from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
    from lab_generate_skill.domain.evidence_sessions import EvidenceSessionEntry
    from evidence_session_fixtures import intent, outcome, resolution

    before = EvidenceSessionSnapshot.model_validate_json(path.read_bytes())
    if before.entries:
        return
    proposed = intent()
    proposed = proposed.model_copy(
        update={
            "operation": proposed.operation.model_copy(
                update={
                    "run_id": before.binding.owner.run_id,
                    "owner_id": before.binding.owner.owner_id,
                }
            )
        }
    )
    entry = EvidenceSessionEntry(
        intent=proposed, outcome=outcome(proposed), resolutions=(resolution(proposed),)
    )
    after = EvidenceSessionSnapshot(
        binding=before.binding, capacity=before.capacity, entries=(entry,)
    )
    assert entry.reusable and after.revision == before.revision + 3
    path.write_bytes(after.model_dump_json().encode())
