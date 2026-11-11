"""Map source-only returned state; generic ownership/progress has no site logic."""

from dataclasses import dataclass
from lab_generate_skill.domain.map_initial_capture import MapInitialEvidence
from .source_qualification_progress import SourceQualificationProgress


@dataclass
class MapSourceProgress(SourceQualificationProgress):
    initial_capture: MapInitialEvidence | None = None
