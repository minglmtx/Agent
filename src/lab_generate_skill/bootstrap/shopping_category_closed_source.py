"""Original category resource/native/first-view/Reset graph, read only."""

import json
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
from lab_generate_skill.domain.closed_shopping_source import (
    ClosedCategoryNavigationReadMaterial,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext, ClosureReceipt
from lab_generate_skill.domain.public_context import PublicContextReceipt
from lab_generate_skill.domain.site_resource import SiteResourceStarted
from lab_generate_skill.domain.state_qualification import (
    EnvironmentSelection,
    ResetSelection,
)
from lab_generate_skill.domain.shopping_navigation_browser_initialization import (
    ShoppingCategoryInitialization,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.sites.shopping.tasks.navigation_state_checks import (
    CategoryNavigationStateChecks,
)
from .shopping_category_closed_preparation import closed_category_preparations
from .shopping_category_initial_capture import CapturedCategoryNavigationInitialChecks


class ClosedCategoryNavigationSourceContexts(ClosedSourceContexts):
    """Exact category wrapper identity, with no publication or live default."""


def closed_category_source_authority(
    material: ClosedCategoryNavigationReadMaterial,
    source: PublicContextReceipt,
    initial: BaselineInputs,
    evidence: EvidenceStore,
    controls: OperationControls,
    operation: OperationContext,
) -> ClosedSourceContextAuthority:
    d = ClosedCategoryNavigationReadMaterial.model_validate(material)
    source = PublicContextReceipt.model_validate(source)
    initial = BaselineInputs.model_validate(initial)
    control = controls.bind(operation)
    browser_closure: ClosureReceipt | None = None
    for spec, record in ((d.site, d.site_record), (d.browser, d.browser_record)):
        reviewed = review_resource(
            record.model_dump(mode="json"), spec.token, evidence, control
        )
        if reviewed["configuration"] != spec.model_dump(mode="json"):
            raise OwnershipConflict(
                "Closed category changed original resource declaration"
            )
        if isinstance(spec, BrowserResourceSpec):
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
    if (
        not isinstance(selected, ShoppingCategoryInitialization)
        or source.scope != d.browser.configuration.spec.scope
        or source.scope != initial.prepared.scope
        or browser != d.browser
        or started.instance.files != d.site.configuration.files
        or selected.site_ref != environment.site_started_ref
        or selected.prepared_ref != initial.prepared_ref
        or selected.endpoint != started.instance.endpoint
        or initial.prepared_ref != d.initial.preparation.prepared_ref
        or len(restoration.closure_refs) != 1
    ):
        raise OwnershipConflict(
            "Closed category changed original measured source/site/initial joins"
        )
    closure = reads.parse(
        restoration.closure_refs[0], "closure-receipt/1", ClosureReceipt, control
    )
    if closure != browser_closure:
        raise OwnershipConflict(
            "Closed category Reset changed original browser closure"
        )
    return ClosedSourceContextAuthority(
        source,
        environment=environment,
        environment_ref=d.environment_ref,
        restoration=restoration,
        restoration_ref=d.reset_ref,
        initial=d.initial,
        browser_closure=closure,
        state_checks=CategoryNavigationStateChecks(evidence),
        initial_checks=CapturedCategoryNavigationInitialChecks(
            evidence, d.capture_intent_ref, d.capture_result_ref
        ),
        preparations=closed_category_preparations(
            initial, d.site, d.browser, evidence, controls
        ),
        evidence=evidence,
        controls=controls,
    )


def closed_category_source_contexts(
    material: ClosedCategoryNavigationReadMaterial,
    evidence: EvidenceStore,
    controls: OperationControls,
    operation: OperationContext,
) -> ClosedCategoryNavigationSourceContexts:
    d = ClosedCategoryNavigationReadMaterial.model_validate(material)
    reads, control = StateReads(evidence), controls.bind(operation)
    receipt = reads.parse(
        d.context_ref, "public-context-receipt/1", PublicContextReceipt, control
    )
    baseline = reads.parse(
        receipt.baseline_ref, "baseline-receipt/1", BaselineReceipt, control
    )
    initial = BaselineEvidenceReader(evidence).verify(baseline, control)
    authority = closed_category_source_authority(
        d, receipt, initial, evidence, controls, operation
    )
    return ClosedCategoryNavigationSourceContexts(
        EvidenceContextRecords(evidence, controls, authority), d.context_ref
    )
