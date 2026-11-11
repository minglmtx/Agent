"""Independent controller read of the original selected native DB publication."""

from pathlib import Path
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.sites.storage_original import (
    OriginalSiteAcquisitionReader,
)
from lab_generate_skill.adapters.map_artifacts.site_access import OriginalMapSiteAccess
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.sites.map.terminal_evidence import TerminalMapEvidence
from lab_generate_skill.sites.map.reference_evidence import (
    reference_artifact,
    read_reference_files,
    MapReferenceRead,
)


def map_database_reference(
    store: EvidenceReader,
    configuration: SiteWorkerConfiguration,
    started: SiteInstanceStarted,
    intent_ref: EvidenceRef,
    result_ref: EvidenceRef,
    terminal: TerminalMapEvidence,
    control: OperationControl,
) -> MapReferenceRead:
    artifact = reference_artifact(store, configuration, intent_ref, result_ref, control)
    access = OriginalMapSiteAccess(
        configuration, "controller", OriginalSiteAcquisitionReader(), None, started
    )
    plan = access.plan(artifact.request.inspection, control)
    if plan != artifact.plan:
        raise OwnershipConflict("Original controller reference plan differs")
    files = MapArtifactReader(plan, Path(plan.workspace_root), access)
    return read_reference_files(
        artifact, terminal, store, configuration, started, files, control
    )
