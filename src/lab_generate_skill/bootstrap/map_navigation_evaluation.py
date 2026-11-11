"""Inject original navigation terminal and native full-file readers into Evaluator."""

from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.ports.initial_observation import InitialObservationReads
from lab_generate_skill.ports.map_state_artifacts import MapStateFileReader
from lab_generate_skill.sites.map.evidence_schema import MapNavigationEvidence
from lab_generate_skill.sites.map.navigation_terminal_evidence import (
    NavigationTerminalEvidence,
)
from lab_generate_skill.sites.map.navigation_evaluation_reads import (
    NavigationEvaluationReads,
)
from lab_generate_skill.evaluators.map.navigation import NavigationEvaluator
from lab_generate_skill.evaluators.evidence import EvaluationEvidence
from .map_navigation_terminal import read_map_navigation_terminal
from .map_overlay_records import map_original_state_reader


def map_navigation_evaluator(
    selected: MapNavigationEvidence,
    preparations: PreparationRecords,
    site: SiteResourceSpec,
    started: SiteResourceStarted,
    operation: OperationContext,
    *,
    files: MapStateFileReader | None = None,
    initials: InitialObservationReads | None = None,
) -> NavigationEvaluator:
    operation = OperationContext.model_validate(operation)

    def terminal(
        store: EvidenceReader, ref: EvidenceRef, control: OperationControl
    ) -> NavigationTerminalEvidence:
        return read_map_navigation_terminal(
            store, preparations, ref, operation, control, initials=initials
        )

    return NavigationEvaluator(
        selected,
        NavigationEvaluationReads(
            site,
            started,
            (
                map_original_state_reader(site.configuration, started.instance)
                if files is None
                else files
            ),
            terminal,
            EvaluationEvidence,
        ),
    )
