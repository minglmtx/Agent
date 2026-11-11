"""Pure immutable export metadata and manifest builders, shared by both callers."""

import hashlib
import json
from lab_generate_skill.domain.export import ExportPlan
from lab_generate_skill.domain.dataset import (
    DatasetManifest,
    DatasetItem,
    TrainingExample,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from .dataset_split import partition_examples


def export_metadata(schema: str) -> EvidenceMetadata:
    return EvidenceMetadata(
        media_type="application/json",
        content_schema=schema,
        visibility="private",
        producer="framework-export-v1",
    )


def example_reference(example: TrainingExample) -> EvidenceRef:
    return evidence_reference(
        example.model_dump_json().encode(), export_metadata("training-example/1")
    )


def make_manifest(
    plan: ExportPlan, plan_ref: EvidenceRef, examples: tuple[TrainingExample, ...]
) -> DatasetManifest:
    templates = {example.template for example in examples}
    if len(templates) != 1:
        raise ValueError(
            "One explicit Generator template per dataset; select compatible export sources"
        )
    partitions = partition_examples(examples, plan.validation_ratio, plan.seed)
    items = tuple(
        DatasetItem.model_validate(
            dict(
                example_id=e.example_id,
                partition=partitions[e.example_id],
                example_ref=example_reference(e),
            )
        )
        for e in examples
    )
    digest = hashlib.sha256(
        json.dumps(
            [i.model_dump(mode="json") for i in items],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return DatasetManifest(
        template=examples[0].template,
        kind=plan.kind,
        export_plan_ref=plan_ref,
        scope_ref=plan.scope_ref,
        split_ref=plan.split_ref,
        status=(
            "awaiting_goal_groups"
            if any(i.partition == "candidate" for i in items)
            else "train_validation_ready"
        ),
        items=items,
        bank_refs=tuple(dict.fromkeys(e.bank_ref for e in examples)),
        review_refs=tuple(dict.fromkeys(e.review_ref for e in examples)),
        examples_sha256=digest,
    )
