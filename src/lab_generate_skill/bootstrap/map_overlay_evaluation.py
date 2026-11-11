"""Single fixed Map evaluator assembly using existing original controller readers."""

from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.sites.map.evidence_schema import (
    MapOverlayEvidence,
    MapCapturePair,
)
from lab_generate_skill.sites.map.evaluation_reads import MapEvaluationReads
from lab_generate_skill.sites.map.terminal_evidence import TerminalMapEvidence
from lab_generate_skill.sites.map.reference_evidence import MapReferenceRead
from lab_generate_skill.evaluators.map.native_overlay import OverlayEvaluator
from lab_generate_skill.evaluators.evidence import EvaluationEvidence
from lab_generate_skill.evaluators.browser_answer import trace_answer
from .map_overlay_records import map_original_state_reader
from .map_terminal_evidence import read_map_terminal_evidence
from .map_database_reference import map_database_reference
from .map_served_evidence import map_reviewed_frontend


def map_overlay_evaluator(
    selected: MapOverlayEvidence,
    preparations: PreparationRecords,
    site: SiteResourceSpec,
    started: SiteResourceStarted,
    operation: OperationContext,
) -> OverlayEvaluator:
    operation = OperationContext.model_validate(operation)

    def terminal(
        store: EvidenceReader, ref: EvidenceRef, control: OperationControl
    ) -> TerminalMapEvidence:
        return read_map_terminal_evidence(store, preparations, ref, operation, control)

    def reference(
        store: EvidenceReader,
        pair: MapCapturePair,
        terminal: TerminalMapEvidence,
        control: OperationControl,
    ) -> MapReferenceRead:
        return map_database_reference(
            store,
            site.configuration,
            started.instance,
            pair.intent_ref,
            pair.result_ref,
            terminal,
            control,
        )

    return OverlayEvaluator(
        selected,
        MapEvaluationReads(
            site,
            started,
            map_original_state_reader(site.configuration, started.instance),
            terminal,
            reference,
            map_reviewed_frontend,
            EvaluationEvidence,
            trace_answer,
        ),
    )
