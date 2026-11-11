"""Existing initial-record reader and fixed category evaluator; no live effects."""

from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.initial_observation import (
    InitialObservationSelection,
    InitialObservationInputs,
)
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.adapters.plans.initial_observation import (
    InitialObservationReader,
)
from lab_generate_skill.sites.shopping.navigation_evidence import (
    CategoryNavigationEvidence,
)
from lab_generate_skill.sites.shopping.navigation_evaluation_reads import (
    CategoryNavigationEvaluationReads,
)
from lab_generate_skill.evaluators.shopping.navigation import (
    CategoryNavigationEvaluator,
)
from .shopping_category_navigation import load_category_navigation_inputs


def shopping_category_evidence_reader(
    preparations: PreparationRecords,
    site: SiteResourceSpec,
    started: SiteResourceStarted,
    operation: OperationContext,
) -> CategoryNavigationEvaluationReads:
    operation = OperationContext.model_validate(operation)
    if preparations is None:
        raise ValueError("Original category preparation authority required")

    def initial(
        reader: EvidenceReader,
        selection: InitialObservationSelection,
        control: OperationControl,
    ) -> InitialObservationInputs:
        return InitialObservationReader(reader, preparations).load(
            selection, operation, control
        )

    return CategoryNavigationEvaluationReads(
        site, started, initial, load_category_navigation_inputs
    )


def shopping_category_evaluator(
    selected: CategoryNavigationEvidence,
    preparations: PreparationRecords,
    site: SiteResourceSpec,
    started: SiteResourceStarted,
    operation: OperationContext,
) -> CategoryNavigationEvaluator:
    return CategoryNavigationEvaluator(
        selected,
        shopping_category_evidence_reader(preparations, site, started, operation),
    )
