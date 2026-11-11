"""Revalidate the same export graph before SFT encoding; never train on labels alone."""

from lab_generate_skill.domain.dataset import TrainingExample, DatasetManifest
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.domain.export import (
    DatasetLoadPlan,
    ExportReceipt,
    ExportPlan,
    ExportScope,
)
from lab_generate_skill.domain.data_scope import SplitManifest
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from .export_targets import ExportDeps
from lab_generate_skill.policies.dataset_manifest import (
    make_manifest,
    example_reference,
)
from .export_examples import prepare_export_examples
from .export_inputs import same_review_source
from .teacher_actor_reads import canonical


def load_dataset(plan: DatasetLoadPlan, deps: ExportDeps) -> LoadedDataset:
    plan = DatasetLoadPlan.model_validate(plan)
    control = deps.controls.bind(plan.operation)
    receipt = canonical(
        plan.export_receipt_ref,
        "export-receipt/1",
        ExportReceipt,
        deps.evidence,
        control,
        4 * 1024**2,
    )
    original = canonical(
        receipt.export_plan_ref,
        "export-plan/1",
        ExportPlan,
        deps.evidence,
        control,
        4 * 1024**2,
    )
    if (
        receipt.kind != plan.expected_kind
        or original.kind != receipt.kind
        or len(original.sources) != len(plan.sources)
    ):
        raise EvidenceIntegrityError(
            "Dataset consumer changed exact original artifact kind/sources"
        )
    for old, current in zip(original.sources, plan.sources, strict=True):
        if (old.example_id, old.legacy_id, old.review_ref, old.qualification_ref) != (
            current.example_id,
            current.legacy_id,
            current.review_ref,
            current.qualification_ref,
        ) or not same_review_source(old.review_read, current.review_read):
            raise EvidenceIntegrityError(
                "Dataset consumer changed original source, target or selected review"
            )
    # Fresh metadata-only read controls. The original published export plan and
    # all model/send/request identities are retained in every output row.
    reading = ExportPlan.model_validate(
        {**original.model_dump(), "sources": plan.sources, "operation": plan.operation}
    )
    scope = canonical(
        original.scope_ref,
        "export-scope/1",
        ExportScope,
        deps.evidence,
        control,
        1024**2,
    )
    split = canonical(
        original.split_ref,
        "data-split/1",
        SplitManifest,
        deps.evidence,
        control,
        16 * 1024**2,
    )
    examples, decisions = prepare_export_examples(
        reading,
        receipt.export_plan_ref,
        scope,
        split,
        deps.inputs,
        deps.authority,
        control,
    )
    if decisions != receipt.decisions or len(examples) != receipt.example_count:
        raise EvidenceIntegrityError(
            "Dataset no longer has the exact qualified original sources/decisions"
        )
    if receipt.dataset_ref is None:
        if examples or receipt.status != "empty":
            raise EvidenceIntegrityError("Empty export unexpectedly contains data")
        return LoadedDataset(receipt, None, (), plan.purpose)
    manifest = canonical(
        receipt.dataset_ref,
        "dataset-manifest/1",
        DatasetManifest,
        deps.evidence,
        control,
        4 * 1024**2,
    )
    if (
        manifest != make_manifest(original, receipt.export_plan_ref, examples)
        or manifest.status != receipt.status
    ):
        raise EvidenceIntegrityError(
            "Manifest changed source/partition/template or dependency identity"
        )
    for item, expected in zip(manifest.items, examples, strict=True):
        saved = canonical(
            item.example_ref,
            "training-example/1",
            TrainingExample,
            deps.evidence,
            control,
            8 * 1024**2,
        )
        if item.example_ref != example_reference(expected) or saved != expected:
            raise EvidenceIntegrityError(
                "Saved SFT example differs from original public input/target/provenance"
            )
    if plan.purpose == "sft" and (
        receipt.kind != "formal"
        or manifest.status != "train_validation_ready"
        or any(not e.labels.formal() for e in examples)
    ):
        raise EvidenceIntegrityError(
            "Parameter training requires qualified formal data and the original viable split"
        )
    control.checkpoint()
    return LoadedDataset(receipt, manifest, examples, plan.purpose)
