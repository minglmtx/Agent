"""Original closed Admin navigation source on existing factual record readers.

Physical raw worker/domain evidence, native state, unique initial return,
authenticated capture and complete Reset are recomputed. No live permission,
claim, native action, model, source retag or candidate equivalence is issued.
"""

from lab_generate_skill.adapters.plans.baseline_evidence import BaselineEvidenceReader
from lab_generate_skill.adapters.plans.closed_context import (
    ClosedSourceContextAuthority,
)
from lab_generate_skill.adapters.plans.closed_resource import review_resource
from lab_generate_skill.adapters.plans.closed_source_records import ClosedSourceContexts
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.storage.context_records import EvidenceContextRecords
from lab_generate_skill.domain.baseline import BaselineInputs, BaselineReceipt
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.closed_source_read import (
    ClosedAdminNavigationReadMaterial,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext, ClosureReceipt
from lab_generate_skill.domain.public_context import PublicContextReceipt
from lab_generate_skill.domain.site_resource import SiteResourceStarted
from lab_generate_skill.domain.state_qualification import (
    EnvironmentSelection,
    ResetSelection,
)
from lab_generate_skill.domain.admin_navigation_browser_initialization import (
    AdminNavigationInitialization,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.sites.shopping_admin.tasks.navigation_state_checks import (
    NavigationStateChecks,
)
from .admin_navigation_closed_preparation import closed_admin_navigation_preparations
from .admin_navigation_initial_capture import CapturedAdminNavigationInitialChecks


class ClosedAdminNavigationSourceContexts(ClosedSourceContexts):
    """Original Admin wrapper identity; same immutable readonly behavior."""


def closed_admin_navigation_source_authority(
    material: ClosedAdminNavigationReadMaterial,
    source: PublicContextReceipt,
    initial: BaselineInputs,
    evidence: EvidenceStore,
    controls: OperationControls,
    operation: OperationContext,
) -> ClosedSourceContextAuthority:
    d = ClosedAdminNavigationReadMaterial.model_validate(material)
    source, initial = PublicContextReceipt.model_validate(
        source
    ), BaselineInputs.model_validate(initial)
    control = controls.bind(operation)
    browser_closure: ClosureReceipt | None = None
    for spec, record in ((d.site, d.site_record), (d.browser, d.browser_record)):
        reviewed = review_resource(
            record.model_dump(mode="json"), spec.token, evidence, control
        )
        if reviewed["configuration"] != spec.model_dump(mode="json"):
            raise OwnershipConflict("Closed Admin acquisition configuration changed")
        if isinstance(spec, BrowserResourceSpec):
            import json

            browser_closure = ClosureReceipt.model_validate_json(
                json.dumps(reviewed["ending"]["closure"])
            )
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
    browser = reads.parse(
        d.initial.browser_spec_ref,
        "browser-resource-spec/4",
        BrowserResourceSpec,
        control,
    )
    selected = d.browser.configuration.initialization
    inputs = d.site.configuration.admin_navigation_inputs
    if (
        inputs is None
        or not isinstance(selected, AdminNavigationInitialization)
        or source.scope != inputs.scope
        or initial.prepared.scope != source.scope
        or browser != d.browser
        or started.instance.files != d.site.configuration.files
        or selected.site_ref != environment.site_started_ref
        or selected.prepared_ref != initial.prepared_ref
        or selected.endpoint != started.instance.endpoint
        or initial.prepared_ref != d.initial.preparation.prepared_ref
    ):
        raise OwnershipConflict(
            "Closed Admin source changed original source/prepared/browser/site joins"
        )
    closure = reads.parse(
        restoration.closure_refs[0], "closure-receipt/1", ClosureReceipt, control
    )
    if closure != browser_closure:
        raise OwnershipConflict(
            "Closed Admin Reset closure differs from original browser ending"
        )
    preparations = closed_admin_navigation_preparations(
        initial, d.site, d.browser, evidence, controls
    )
    return ClosedSourceContextAuthority(
        source,
        environment=environment,
        environment_ref=d.environment_ref,
        restoration=restoration,
        restoration_ref=d.reset_ref,
        initial=d.initial,
        browser_closure=closure,
        state_checks=NavigationStateChecks(evidence),
        initial_checks=CapturedAdminNavigationInitialChecks(
            evidence, d.capture_intent_ref, d.capture_result_ref
        ),
        preparations=preparations,
        evidence=evidence,
        controls=controls,
    )


def closed_admin_navigation_source_contexts(
    material: ClosedAdminNavigationReadMaterial,
    evidence: EvidenceStore,
    controls: OperationControls,
    operation: OperationContext,
) -> ClosedAdminNavigationSourceContexts:
    d = ClosedAdminNavigationReadMaterial.model_validate(material)
    reads = StateReads(evidence)
    control = controls.bind(operation)
    receipt = reads.parse(
        d.context_ref, "public-context-receipt/1", PublicContextReceipt, control
    )
    baseline = reads.parse(
        receipt.baseline_ref, "baseline-receipt/1", BaselineReceipt, control
    )
    initial = BaselineEvidenceReader(evidence).verify(baseline, control)
    authority = closed_admin_navigation_source_authority(
        d, receipt, initial, evidence, controls, operation
    )
    return ClosedAdminNavigationSourceContexts(
        EvidenceContextRecords(evidence, controls, authority), d.context_ref
    )
