"""Original controller capability for complete immutable frontend source review."""

from lab_generate_skill.adapters.browsergym.storage_original import (
    OriginalBrowserAcquisitionReader,
)
from lab_generate_skill.adapters.map_artifacts.browser_access import (
    OriginalMapBrowserAccess,
)
from lab_generate_skill.adapters.map_artifacts.browser_sources import (
    OriginalMapBrowserSources,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.terminal_evidence import TerminalMapEvidence
from lab_generate_skill.sites.map.served_evidence import reviewed_frontend_served


def map_reviewed_frontend(
    terminal: TerminalMapEvidence, control: OperationControl
) -> bool:
    cfg = terminal.initial.browser.configuration
    inputs = cfg.map_inputs
    if inputs is None:
        raise EvidenceIntegrityError("Original Map source inputs required")
    access = OriginalMapBrowserAccess(
        cfg, "controller", OriginalBrowserAcquisitionReader(), None
    )
    originals = OriginalMapBrowserSources(inputs, access).read(control)
    return reviewed_frontend_served(terminal, originals, control)
