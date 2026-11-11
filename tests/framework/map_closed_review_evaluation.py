"""Same original Map rules/readers after closure; no live controller impersonation."""

from pathlib import Path
from typing import overload
from lab_generate_skill.bootstrap.map_navigation_terminal import (
    read_map_navigation_terminal,
)
from lab_generate_skill.sites.map.navigation_terminal_evidence import (
    NavigationTerminalEvidence,
)
from lab_generate_skill.sites.map.navigation_evaluation_reads import (
    NavigationEvaluationReads,
)
from lab_generate_skill.evaluators.map.navigation import NavigationEvaluator
from lab_generate_skill.evaluators.evidence import EvaluationEvidence
from lab_generate_skill.evaluators.browser_answer import trace_answer
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.adapters.map_artifacts.state_reader import (
    OriginalMapStateReader,
)
from lab_generate_skill.adapters.plans.initial_observation import (
    InitialObservationReader,
)
from lab_generate_skill.adapters.map_artifacts.browser_sources import (
    OriginalMapBrowserSources,
)
from lab_generate_skill.sites.map.served_evidence import reviewed_frontend_served
from lab_generate_skill.domain.baseline import BaselineInputs
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.site_resource import SiteResourceStarted
from lab_generate_skill.domain.map_terminal_evidence import MapTerminalSelection
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.state_qualification import (
    ResetSelection,
    QualifiedResetChecks,
)
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.sites.map.evidence_schema import (
    MapOverlayEvidence,
    MapNavigationEvidence,
    MapCapturePair,
)
from lab_generate_skill.sites.map.evaluation_reads import MapEvaluationReads
from lab_generate_skill.sites.map.terminal_evidence import (
    TerminalMapEvidence,
    terminal_evidence,
)
from lab_generate_skill.sites.map.reference_evidence import (
    MapReferenceRead,
    reference_artifact,
    read_reference_files,
)
from lab_generate_skill.sites.map.tasks.overlay_state_checks import OverlayStateChecks
from lab_generate_skill.evaluators.map.native_overlay import OverlayEvaluator
from source_actor_review import read_fact
from source_review_records import ReadOnlyEvidence
from map_closed_review_access import ClosedMapReviewAccess
from map_closed_review_records import preparations


class ClosedMapEvaluation:
    def __init__(
        self,
        access: ClosedMapReviewAccess,
        initial: BaselineInputs,
        started: SiteResourceStarted,
        store: ReadOnlyEvidence,
        controls: OperationControls,
        operation: OperationContext,
    ) -> None:
        self.access, self.started, self.store, self.operation = (
            access,
            started,
            store,
            operation,
        )
        if operation.mode != "cleanup" or (
            operation.run_id,
            operation.owner_id,
            operation.attempt_id,
        ) != (
            initial.prepared.scope.owner.run_id,
            initial.prepared.scope.owner.owner_id,
            initial.prepared.scope.attempt_id,
        ):
            raise OwnershipConflict("Closed Map review changed original attempt")
        self.files = OriginalMapStateReader(
            Path(access.site.configuration.files.workspace_root), access, access
        )
        self.preparations = preparations(initial, access, self.files, store, controls)

    def terminal(
        self, store: EvidenceReader, ref: EvidenceRef, control: OperationControl
    ) -> TerminalMapEvidence:
        if store is not self.store:
            raise OwnershipConflict(
                "Independent Map review changed read-only evidence store"
            )
        selected = read_fact(self.store, ref, MapTerminalSelection, control)
        initial = InitialObservationReader(self.store, self.preparations).load(
            selected.initial, self.operation, control
        )
        if initial.browser != self.access.browser:
            raise OwnershipConflict("Map terminal changed original closed browser")
        plan = self.access.browser_plan
        return terminal_evidence(
            selected,
            initial,
            self.store,
            MapArtifactReader(plan, Path(plan.workspace_root), self.access),
            control,
        )

    def reference(
        self,
        store: EvidenceReader,
        pair: MapCapturePair,
        terminal: TerminalMapEvidence,
        control: OperationControl,
    ) -> MapReferenceRead:
        if store is not self.store:
            raise OwnershipConflict(
                "Independent Map review changed read-only evidence store"
            )
        cfg = self.access.site.configuration
        artifact = reference_artifact(
            store, cfg, pair.intent_ref, pair.result_ref, control
        )
        plan = self.access.plan(artifact.request.inspection, control)
        if plan != artifact.plan:
            raise OwnershipConflict("Closed Map DB files changed original request plan")
        files = MapArtifactReader(plan, Path(plan.workspace_root), self.access)
        return read_reference_files(
            artifact, terminal, store, cfg, self.started.instance, files, control
        )

    def served(self, terminal: TerminalMapEvidence, control: OperationControl) -> bool:
        if terminal.initial.browser != self.access.browser:
            raise OwnershipConflict("Closed Map source review changed original browser")
        inputs = self.access.browser.configuration.map_inputs
        assert inputs is not None
        originals = OriginalMapBrowserSources(inputs, self.access).read(control)
        return reviewed_frontend_served(terminal, originals, control)

    def navigation_terminal(
        self, store: EvidenceReader, ref: EvidenceRef, control: OperationControl
    ) -> NavigationTerminalEvidence:
        if store is not self.store:
            raise OwnershipConflict(
                "Independent navigation changed read-only evidence store"
            )
        value = read_map_navigation_terminal(
            store, self.preparations, ref, self.operation, control
        )
        if value.initial.browser != self.access.browser:
            raise OwnershipConflict(
                "Navigation terminal changed original closed browser"
            )
        return value

    @overload
    def evaluator(self, selected: MapOverlayEvidence) -> OverlayEvaluator: ...

    @overload
    def evaluator(self, selected: MapNavigationEvidence) -> NavigationEvaluator: ...

    def evaluator(
        self, selected: MapOverlayEvidence | MapNavigationEvidence
    ) -> OverlayEvaluator | NavigationEvaluator:
        if isinstance(selected, MapNavigationEvidence):
            return NavigationEvaluator(
                selected,
                NavigationEvaluationReads(
                    self.access.site,
                    self.started,
                    self.files,
                    self.navigation_terminal,
                    EvaluationEvidence,
                ),
            )
        return OverlayEvaluator(
            selected,
            MapEvaluationReads(
                self.access.site,
                self.started,
                self.files,
                self.terminal,
                self.reference,
                self.served,
                EvaluationEvidence,
                trace_answer,
            ),
        )

    def reset(
        self, reference: EvidenceRef, control: OperationControl
    ) -> QualifiedResetChecks:
        selected = read_fact(self.store, reference, ResetSelection, control)
        return OverlayStateChecks(
            self.store, self.files, self.access.site, self.started
        ).reset(selected, reference, control)
