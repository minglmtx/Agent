"""Actual original Shopping category source publication after complete restore/domain close.

The existing fixed readonly worker runs original state/context publishers'
validation; this same authorized original parent alone persists and seals.
Proposed/partial bytes never constitute a qualified source or execution grant.
"""

from dataclasses import dataclass
from .shopping_category_closed_source import ClosedCategoryNavigationSourceContexts
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.plans.closed_source_records import (
    ClosedSourceContexts,
    SupervisedClosedSourceContexts,
)
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.domain.baseline import BaselineInputs, BaselineReceipt
from lab_generate_skill.domain.reset import ResetInputs, ResetReceipt
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.lifecycle import ResourceRecord, OperationContext
from lab_generate_skill.domain.closed_shopping_source import (
    ClosedCategoryNavigationReadMaterial,
)
from lab_generate_skill.domain.closed_source_read import ClosedSourcePublicationInput
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.public_context import (
    PublicContextInputs,
    PublicContextReceipt,
    assemble_public_context,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControls


@dataclass(frozen=True)
class ClosedCategoryNavigationFacts:
    environment_ref: EvidenceRef
    reset_selection_ref: EvidenceRef
    initial: InitialObservationSelection
    capture_intent_ref: EvidenceRef
    capture_result_ref: EvidenceRef
    site: SiteResourceSpec
    browser: BrowserResourceSpec
    site_record: ResourceRecord
    browser_record: ResourceRecord
    baseline_inputs: BaselineInputs
    baseline: BaselineReceipt
    reset_inputs: ResetInputs
    reset: ResetReceipt
    source_prefix_reuse: dict[str, int] | None = None


@dataclass(frozen=True)
class PublishedCategoryNavigationSource:
    material: ClosedCategoryNavigationReadMaterial
    receipt: PublicContextReceipt
    contexts: ClosedCategoryNavigationSourceContexts
    inputs: PublicContextInputs
    source_prefix_reuse: dict[str, int] | None = None


def metadata(schema: str, visibility: str, producer: str) -> EvidenceMetadata:
    return EvidenceMetadata.model_validate(
        dict(
            media_type="application/json",
            content_schema=schema,
            visibility=visibility,
            producer=producer,
        )
    )


def publish_category_navigation_source(
    owner: OriginalSourceQualificationOwner,
    facts: ClosedCategoryNavigationFacts,
    operation: OperationContext,
    controls: OperationControls,
    *,
    source_reads: ClosedSourceReadTransport,
) -> PublishedCategoryNavigationSource:
    if (
        not isinstance(owner, OriginalSourceQualificationOwner)
        or not isinstance(facts, ClosedCategoryNavigationFacts)
        or not isinstance(source_reads, ClosedSourceReadTransport)
    ):
        raise TypeError(
            "Actual original Shopping category source owner/facts and controlled reader required"
        )
    operation = OperationContext.model_validate(operation)
    control = controls.bind(operation)
    owner.require(operation, control, new_work=True)
    f, store = facts, owner.evidence
    if (
        source_reads.store is not store
        or f.baseline.scope != owner.scope
        or f.reset.scope != owner.scope
        or f.baseline_inputs.prepared.scope != owner.scope
        or f.reset_inputs.plan.scope != owner.scope
        or (f.site.token.owner, f.site.slurm.execution, f.site.slurm.parent)
        != (owner.scope.owner, owner.execution, owner.controller)
    ):
        raise OwnershipConflict(
            "Shopping category publication changed original measured source/store/owner"
        )
    baseline_meta = metadata("baseline-receipt/1", "private", "state-records-v1")
    reset_meta = metadata("reset-receipt/1", "private", "state-records-v1")
    baseline_ref = evidence_reference(
        f.baseline.model_dump_json().encode(), baseline_meta
    )
    reset_ref = evidence_reference(f.reset.model_dump_json().encode(), reset_meta)
    public = PublicConstructionContext(
        context_id=owner.scope.context_id,
        task=f.baseline_inputs.public_task,
        initial_observation_ref=f.baseline.observation_ref,
    )
    public_meta = metadata(
        public.schema_version, "public", "source-qualification-context-v1"
    )
    public_ref = evidence_reference(public.model_dump_json().encode(), public_meta)
    inputs = PublicContextInputs(
        context=public,
        context_ref=public_ref,
        baseline_inputs=f.baseline_inputs,
        baseline=f.baseline,
        baseline_ref=baseline_ref,
        reset_inputs=f.reset_inputs,
        reset=f.reset,
        reset_ref=reset_ref,
    )
    receipt = assemble_public_context(inputs, operation)
    receipt_meta = metadata(receipt.schema_version, "private", "context-records-v1")
    reference = evidence_reference(receipt.model_dump_json().encode(), receipt_meta)
    material = ClosedCategoryNavigationReadMaterial(
        context_ref=reference,
        environment_ref=f.environment_ref,
        reset_ref=f.reset_selection_ref,
        initial=f.initial,
        capture_intent_ref=f.capture_intent_ref,
        capture_result_ref=f.capture_result_ref,
        site=f.site,
        browser=f.browser,
        site_record=f.site_record,
        browser_record=f.browser_record,
    )
    known: list[EvidenceRef] = []
    try:
        source_reads.require_current(material, operation)
        proposed = ClosedSourcePublicationInput(
            public=public, baseline=f.baseline, reset=f.reset, context=receipt
        )
        if source_reads.read(material, control, publication=proposed) != receipt:
            raise OwnershipConflict(
                "Original installed Shopping category publication proof changed source"
            )
        owner.require(operation, control, new_work=True)
        for value, meta, expected in (
            (public, public_meta, public_ref),
            (f.baseline, baseline_meta, baseline_ref),
            (f.reset, reset_meta, reset_ref),
            (receipt, receipt_meta, reference),
        ):
            actual = store.put(value.model_dump_json().encode(), meta, control=control)
            known.append(actual)
            if actual != expected:
                raise OwnershipConflict(
                    "Original Shopping category source summary publication changed bytes"
                )
        contexts = ClosedCategoryNavigationSourceContexts(
            SupervisedClosedSourceContexts(material, source_reads, controls), reference
        )
        checked, checked_inputs = contexts.load_context_inputs(reference, operation)
        if checked != receipt or checked_inputs != inputs:
            raise OwnershipConflict(
                "Original installed Shopping category closed reader changed publication"
            )
        owner.seal(operation, control)
        return PublishedCategoryNavigationSource(
            material, receipt, contexts, checked_inputs, f.source_prefix_reuse
        )
    except BaseException as error:
        setattr(error, "source_qualification_known_references", tuple(known))
        setattr(error, "source_qualification_candidate_reference", reference)
        setattr(
            error,
            "source_qualification_candidates",
            (public_ref, baseline_ref, reset_ref, reference),
        )
        raise
