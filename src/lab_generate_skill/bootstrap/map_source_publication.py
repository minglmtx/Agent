"""Publish original measured source summaries after its full domain closure.

Existing state/context record ports and the existing independent closed-source
authority do the verification. No second baseline algorithm, initialization,
restore, model call, claim, runner or source identity substitution is introduced.
"""

from dataclasses import dataclass
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.adapters.storage.state_records import EvidenceStateRecords
from lab_generate_skill.adapters.storage.context_records import EvidenceContextRecords
from lab_generate_skill.domain.baseline import BaselineInputs, BaselineReceipt
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.lifecycle import OperationContext, ResourceRecord
from lab_generate_skill.domain.map_initial_capture import MapInitialEvidence
from lab_generate_skill.domain.public_context import (
    PublicContextInputs,
    PublicContextReceipt,
    assemble_public_context,
)
from lab_generate_skill.domain.reset import ResetInputs, ResetReceipt
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.ports.lifecycle import Clock, OperationControls
from lab_generate_skill.ports.contexts import ContextRecords
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.plans.closed_source_records import (
    SupervisedClosedSourceContexts,
)
from lab_generate_skill.domain.closed_source_read import (
    ClosedMapReadMaterial,
    ClosedSourcePublicationInput,
)
from .map_closed_source import (
    ClosedMapSourceDeclarations,
    ClosedMapSourceContexts,
    closed_map_source_context_authority,
    closed_map_source_contexts,
)


@dataclass(frozen=True)
class ClosedMapQualificationFacts:
    """Original objects/refs, without inventing a future context receipt reference."""

    environment_ref: EvidenceRef
    reset_selection_ref: EvidenceRef
    initial: InitialObservationSelection
    initial_capture: MapInitialEvidence
    site: SiteResourceSpec
    browser: BrowserResourceSpec
    site_record: ResourceRecord
    browser_record: ResourceRecord
    baseline_inputs: BaselineInputs
    baseline: BaselineReceipt
    reset_inputs: ResetInputs
    reset: ResetReceipt


@dataclass(frozen=True)
class PublishedClosedMapQualification:
    declarations: ClosedMapSourceDeclarations
    receipt: PublicContextReceipt
    contexts: ClosedMapSourceContexts
    inputs: PublicContextInputs
    source_prefix_reuse: dict[str, int] | None = None


def _metadata(schema: str, visibility: str, producer: str) -> EvidenceMetadata:
    return EvidenceMetadata.model_validate(
        {
            "media_type": "application/json",
            "content_schema": schema,
            "visibility": visibility,
            "producer": producer,
        }
    )


def publish_closed_map_qualification(
    owner: OriginalSourceQualificationOwner,
    facts: ClosedMapQualificationFacts,
    operation: OperationContext,
    controls: OperationControls,
    clock: Clock,
    *,
    metadata_seconds: int,
    source_reads: ClosedSourceReadTransport | None = None,
) -> PublishedClosedMapQualification:
    if not isinstance(owner, OriginalSourceQualificationOwner) or not isinstance(
        facts, ClosedMapQualificationFacts
    ):
        raise TypeError(
            "Actual original source owner and complete closed source facts required"
        )
    if type(metadata_seconds) is not int or not 1 <= metadata_seconds <= 3600:
        raise ValueError("Explicit bounded original source metadata duration required")
    operation = OperationContext.model_validate(operation)
    control = controls.bind(operation)
    owner.require(operation, control, new_work=True)
    f = facts
    if (
        f.baseline.scope != owner.scope
        or f.reset.scope != owner.scope
        or f.baseline_inputs.prepared.scope != owner.scope
        or f.reset_inputs.plan.scope != owner.scope
        or (f.site.token.owner, f.site.slurm.execution, f.site.slurm.parent)
        != (owner.scope.owner, owner.execution, owner.controller)
        or f.browser.configuration.spec.scope != owner.scope
        or f.site_record.state != "closed"
        or f.browser_record.state != "closed"
    ):
        raise OwnershipConflict(
            "Source publication cannot change original measured scope or closure"
        )
    store = owner.evidence
    # Predict only identities of these already assembled exact immutable bytes.
    # They cannot be consumed until the original record ports acknowledge them.
    baseline_ref = evidence_reference(
        f.baseline.model_dump_json().encode(),
        _metadata("baseline-receipt/1", "private", "state-records-v1"),
    )
    reset_ref = evidence_reference(
        f.reset.model_dump_json().encode(),
        _metadata("reset-receipt/1", "private", "state-records-v1"),
    )
    public = PublicConstructionContext(
        context_id=owner.scope.context_id,
        task=f.baseline_inputs.public_task,
        initial_observation_ref=f.baseline.observation_ref,
    )
    public_raw = public.model_dump_json().encode()
    public_metadata = _metadata(
        public.schema_version, "public", "source-qualification-context-v1"
    )
    public_ref = evidence_reference(public_raw, public_metadata)
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
    reference = evidence_reference(
        receipt.model_dump_json().encode(),
        _metadata(receipt.schema_version, "private", "context-records-v1"),
    )
    declarations = ClosedMapSourceDeclarations(
        context_ref=reference,
        environment_ref=f.environment_ref,
        reset_ref=f.reset_selection_ref,
        initial=f.initial,
        initial_capture=f.initial_capture,
        site=f.site,
        browser=f.browser,
        site_record=f.site_record,
        browser_record=f.browser_record,
    )
    known: list[EvidenceRef] = []
    try:
        if source_reads is None:
            # Actual original resource records and strict raw physical evidence are
            # verified before summary publication, using the same reader authority.
            authority = closed_map_source_context_authority(
                declarations,
                receipt,
                f.baseline_inputs,
                store,
                controls,
                operation,
            )
            states = EvidenceStateRecords(store, controls, authority)
            contexts = EvidenceContextRecords(store, controls, authority)
            if store.put(public_raw, public_metadata, control=control) != public_ref:
                raise OwnershipConflict(
                    "Public source projection publication changed bytes"
                )
            known.append(public_ref)
            baseline_op = f.baseline.operation.cleanup(
                operation.operation_id + ".baseline-publication",
                now=clock.utcnow(),
                seconds=min(metadata_seconds, control.checkpoint()),
            )
            actual_baseline = states.publish_baseline(f.baseline, baseline_op)
            known.append(actual_baseline)
            if actual_baseline != baseline_ref:
                raise OwnershipConflict(
                    "Closed source baseline publication changed original bytes"
                )
            reset_op = f.reset.operation.cleanup(
                operation.operation_id + ".reset-publication",
                now=clock.utcnow(),
                seconds=min(metadata_seconds, control.checkpoint()),
            )
            actual_reset = states.publish_reset(f.reset, reset_op)
            known.append(actual_reset)
            if actual_reset != reset_ref:
                raise OwnershipConflict(
                    "Closed source Reset publication changed original bytes"
                )
            actual = contexts.publish_context(receipt, operation)
            known.append(actual)
            if actual != reference:
                raise OwnershipConflict(
                    "Closed source context publication changed original bytes"
                )
        else:
            material = ClosedMapReadMaterial.model_validate(vars(declarations))
            source_reads.require_current(material, operation)
            proposed = ClosedSourcePublicationInput(
                public=public,
                baseline=f.baseline,
                reset=f.reset,
                context=receipt,
            )
            if source_reads.read(material, control, publication=proposed) != receipt:
                raise OwnershipConflict(
                    "Original installed publication validation changed source"
                )
            # The same original publishers ran their full verification in the
            # supervised readonly child. Only this fresh authorized original
            # parent now persists the exact checked bytes. Partial publication
            # never seals or grants qualification, even if a write committed.
            owner.require(operation, control, new_work=True)
            for value, metadata, expected in (
                (public, public_metadata, public_ref),
                (
                    f.baseline,
                    _metadata("baseline-receipt/1", "private", "state-records-v1"),
                    baseline_ref,
                ),
                (
                    f.reset,
                    _metadata("reset-receipt/1", "private", "state-records-v1"),
                    reset_ref,
                ),
                (
                    receipt,
                    _metadata(receipt.schema_version, "private", "context-records-v1"),
                    reference,
                ),
            ):
                actual = store.put(
                    value.model_dump_json().encode(), metadata, control=control
                )
                known.append(actual)
                if actual != expected:
                    raise OwnershipConflict(
                        "Verified original summary publication changed bytes"
                    )
        reader: ClosedMapSourceContexts
        if source_reads is None:
            reader = closed_map_source_contexts(
                declarations, store, controls, operation
            )
        else:
            reader = ClosedMapSourceContexts(
                SupervisedClosedSourceContexts(
                    ClosedMapReadMaterial.model_validate(vars(declarations)),
                    source_reads,
                    controls,
                ),
                reference,
            )
        checked, checked_inputs = reader.load_context_inputs(reference, operation)
        if checked != receipt or checked_inputs != inputs:
            raise OwnershipConflict(
                "Closed source reader returned another qualification"
            )
        owner.seal(operation, control)
        return PublishedClosedMapQualification(
            declarations, receipt, reader, checked_inputs
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
