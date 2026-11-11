"""Assemble historical source readers after actual original Map domain closure.

The returned context port has no permission to publish, compare a candidate or
execute a task. Actual run/source/claim admission stays at the existing entry.
"""

from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.adapters.map_artifacts.closed_access import (
    ClosedMapSourceAccess,
)
from lab_generate_skill.adapters.map_artifacts.state_reader import (
    OriginalMapStateReader,
)
from lab_generate_skill.adapters.plans.baseline_evidence import BaselineEvidenceReader
from lab_generate_skill.adapters.plans.closed_context import (
    ClosedSourceContextAuthority,
)
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.storage.context_records import EvidenceContextRecords
from lab_generate_skill.domain.baseline import BaselineReceipt, BaselineInputs
from lab_generate_skill.domain.initial_equivalence import EquivalenceReceipt
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.lifecycle import (
    OperationContext,
    ResourceRecord,
    ClosureReceipt,
)
from lab_generate_skill.domain.map_initial_capture import MapInitialEvidence
from lab_generate_skill.domain.map_navigation_browser_initialization import (
    MapNavigationInitialization,
)
from lab_generate_skill.domain.public_context import PublicContextReceipt
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.state_qualification import (
    EnvironmentSelection,
    ResetSelection,
)
from lab_generate_skill.ports.contexts import ContextRecords
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.sites.map.tasks.navigation_initial_observation import (
    NavigationInitialObservationChecks,
)
from lab_generate_skill.sites.map.tasks.overlay_state_checks import OverlayStateChecks
from .map_closed_preparation import closed_map_preparations
from lab_generate_skill.adapters.plans.closed_source_records import ClosedSourceContexts


@dataclass(frozen=True)
class ClosedMapSourceDeclarations:
    context_ref: EvidenceRef
    environment_ref: EvidenceRef
    reset_ref: EvidenceRef
    initial: InitialObservationSelection
    initial_capture: MapInitialEvidence
    site: SiteResourceSpec
    browser: BrowserResourceSpec
    site_record: ResourceRecord
    browser_record: ResourceRecord


class ClosedMapSourceContexts(ClosedSourceContexts):
    """Preserved original Map wrapper identity on the shared readonly guard."""


def closed_map_source_context_authority(
    declarations: ClosedMapSourceDeclarations,
    source: PublicContextReceipt,
    initial: BaselineInputs,
    evidence: EvidenceStore,
    controls: OperationControls,
    operation: OperationContext,
) -> ClosedSourceContextAuthority:
    """Same closed physical/factual verifier for readers and original publishers.

    Accepts the actual measured objects before their summary publication. It
    grants no new source/task claim; the publisher separately checks its actual
    original physical caller and must use existing immutable record ports.
    """
    if not isinstance(declarations, ClosedMapSourceDeclarations):
        raise TypeError("Explicit original closed Map source declarations required")
    source = PublicContextReceipt.model_validate(source)
    initial = BaselineInputs.model_validate(initial)
    d = declarations
    control = controls.bind(operation)
    access = ClosedMapSourceAccess(
        d.site, d.browser, d.site_record, d.browser_record, evidence, control
    )
    selected = d.browser.configuration.initialization
    if not isinstance(selected, MapNavigationInitialization):
        raise OwnershipConflict("Explicit navigation source initialization required")
    reads = StateReads(evidence)
    environment = reads.parse(
        d.environment_ref, "environment-selection/1", EnvironmentSelection, control
    )
    restoration = reads.parse(d.reset_ref, "reset-selection/1", ResetSelection, control)
    started = reads.parse(
        environment.site_started_ref,
        "site-resource-started/1",
        SiteResourceStarted,
        control,
    )
    inputs = d.site.configuration.map_inputs
    if (
        inputs is None
        or source.scope != inputs.scope
        or reads.parse(
            d.initial.browser_spec_ref,
            "browser-resource-spec/4",
            BrowserResourceSpec,
            control,
        )
        != d.browser
        or started.instance.files != d.site.configuration.files
    ):
        raise OwnershipConflict(
            "Closed source declarations changed original scope/browser/site"
        )
    files = OriginalMapStateReader(
        Path(d.site.configuration.files.workspace_root), access, access
    )
    preparations = closed_map_preparations(initial, access, files, evidence, controls)
    closure = reads.parse(
        restoration.closure_refs[0], "closure-receipt/1", ClosureReceipt, control
    )
    authority = ClosedSourceContextAuthority(
        source,
        environment=environment,
        environment_ref=d.environment_ref,
        restoration=restoration,
        restoration_ref=d.reset_ref,
        initial=d.initial,
        browser_closure=closure,
        state_checks=OverlayStateChecks(evidence, files, d.site, started),
        initial_checks=NavigationInitialObservationChecks(
            evidence, d.initial_capture, selected
        ),
        preparations=preparations,
        evidence=evidence,
        controls=controls,
    )
    # Qualification must retain the closure from the original browser ending.
    if closure != access.browser_closure:
        raise OwnershipConflict(
            "Source Reset closure differs from original browser ending"
        )
    return authority


def closed_map_source_contexts(
    declarations: ClosedMapSourceDeclarations,
    evidence: EvidenceStore,
    controls: OperationControls,
    operation: OperationContext,
) -> ClosedMapSourceContexts:
    if not isinstance(declarations, ClosedMapSourceDeclarations):
        raise TypeError("Explicit original closed Map source declarations required")
    d = declarations
    control = controls.bind(operation)
    reads = StateReads(evidence)
    source = reads.parse(
        d.context_ref, "public-context-receipt/1", PublicContextReceipt, control
    )
    baseline = reads.parse(
        source.baseline_ref, "baseline-receipt/1", BaselineReceipt, control
    )
    initial = BaselineEvidenceReader(evidence).verify(baseline, control)
    authority = closed_map_source_context_authority(
        d, source, initial, evidence, controls, operation
    )
    contexts = ClosedMapSourceContexts(
        EvidenceContextRecords(evidence, controls, authority), d.context_ref
    )
    # Assemble a read-only port. Every consumer calls load_context before its
    # source/claim decision; that method retains the complete original proof.
    # An eager identical load here duplicated it without returning any fact.
    return contexts
