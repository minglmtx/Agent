"""Keep construction entry signatures while injecting its business source proofs.

All phase/declaration/lifecycle logic remains in the shared implementations.
Single tasks inject their own source implementations at bootstrap.
"""

from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.ports.construction_task_execution import TaskExecutionAuthority
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.claims import SourceClaims
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.task_finalization import (
    TaskFinalizationAuthority as FinalizationSource,
)
from lab_generate_skill.ports.trace_journal import TraceJournal
from collections.abc import Callable
from .construction_task_phase_source import (
    ConstructionTaskPhaseSources,
    ConstructionTaskPhaseResources,
)
from .task_preparation_admission import TaskPreparationAuthority
from .task_initialization_admission import TaskInitializationAuthority
from .task_capture_admission import TaskCaptureAuthority
from .task_finalization_admission import TaskFinalizationAuthority


class ConstructionTaskPreparationAuthority(TaskPreparationAuthority):
    def __init__(
        self,
        construction: ConstructionJournal,
        runs: RunJournal,
        authority: TaskExecutionAuthority,
        evidence: EvidenceStore,
    ) -> None:
        sources = ConstructionTaskPhaseSources(construction)
        super().__init__(
            sources, runs, ConstructionTaskPhaseResources(sources, authority), evidence
        )


class ConstructionTaskInitializationAuthority(TaskInitializationAuthority):
    def __init__(
        self,
        declaration_ref: EvidenceRef,
        construction: ConstructionJournal,
        runs: RunJournal,
        authority: TaskExecutionAuthority,
        evidence: EvidenceStore,
    ) -> None:
        sources = ConstructionTaskPhaseSources(construction)
        super().__init__(
            declaration_ref,
            sources,
            runs,
            ConstructionTaskPhaseResources(sources, authority),
            evidence,
        )


class ConstructionTaskCaptureAuthority(TaskCaptureAuthority):
    def __init__(
        self,
        declaration_ref: EvidenceRef,
        construction: ConstructionJournal,
        runs: RunJournal,
        authority: TaskExecutionAuthority,
        trace: Callable[[], TraceJournal],
        evidence: EvidenceStore,
    ) -> None:
        sources = ConstructionTaskPhaseSources(construction)
        super().__init__(
            declaration_ref,
            sources,
            runs,
            ConstructionTaskPhaseResources(sources, authority),
            trace,
            evidence,
        )


class ConstructionTaskFinalizationAuthority(TaskFinalizationAuthority):
    def __init__(
        self,
        declaration_ref: EvidenceRef,
        construction: ConstructionJournal,
        runs: RunJournal,
        claims: SourceClaims,
        plans: RunPlans,
        source: FinalizationSource,
        evidence: EvidenceStore,
    ) -> None:
        super().__init__(
            declaration_ref,
            ConstructionTaskPhaseSources(construction),
            runs,
            claims,
            plans,
            source,
            evidence,
        )
