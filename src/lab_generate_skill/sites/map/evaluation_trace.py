"""Original MapData publication audit over the shared sealed browser trace."""

from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evaluation_evidence import (
    EvaluationEvidenceReader,
    TraceAnswerReader,
)
from .terminal_evidence import TerminalMapEvidence
from .evidence_schema import MapOverlayEvidence
from .page_health import MapPageHealth
from .sealed_browser_trace import sealed_browser_trace


def sealed_map_trace(
    selected: MapOverlayEvidence,
    terminal: TerminalMapEvidence,
    page: MapPageHealth,
    reads: EvaluationEvidenceReader,
    answer_reader: TraceAnswerReader,
) -> InteractionTrace:
    assert selected.trace_ref is not None and selected.trace_snapshot_ref is not None
    trace, originals = sealed_browser_trace(
        selected.trace_ref,
        selected.trace_snapshot_ref,
        terminal,
        page,
        reads,
        answer_reader,
    )
    observed = [
        p["original_readout"] for p in terminal.pages if p["phase"] == "unique_return"
    ]
    if (
        observed != [r.model_dump(mode="json") for r in originals]
        or originals[-1] != terminal.readout
    ):
        raise EvidenceIntegrityError(
            "Map terminal pages differ from original Actor interactions"
        )
    return trace
