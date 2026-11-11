"""Read exact parent-qualified immutable rows, never confer source/phase admission.

The registered parent must first use the original load_dataset and real phase
authority. This child rechecks its exact bytes; formal labels are not authority.
No alternate JSONL, path discovery, train/dev selection or repair exists here.
"""

import hashlib
from typing import TypeVar
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.training import TrainingPlan
from lab_generate_skill.domain.dataset import TrainingExample, DatasetManifest
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.domain.export import ExportReceipt
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.wire_json import json_object
from lab_generate_skill.policies.training_admission import require_training_dataset

T = TypeVar("T", bound=Contract)


def original_document(
    ref: EvidenceRef,
    model: type[T],
    evidence: EvidenceReader,
    control: OperationControl,
) -> T:
    if (
        ref.visibility != "private"
        or ref.media_type != "application/json"
        or ref.size_bytes > 8 * 1024**2
    ):
        raise EvidenceIntegrityError(
            "Original bounded private training document required"
        )
    control.checkpoint()
    raw = evidence.read(ref, control)
    if (
        type(raw) is not bytes
        or len(raw) != ref.size_bytes
        or hashlib.sha256(raw).hexdigest() != ref.sha256
    ):
        raise EvidenceIntegrityError("Original training document changed size/digest")
    json_object(raw)
    result = model.model_validate_json(raw)
    if (
        result.model_dump_json().encode() != raw
        or getattr(result, "schema_version", None) != ref.content_schema
    ):
        raise EvidenceIntegrityError("Original training document must be canonical")
    control.checkpoint()
    return result


def read_training_data(
    plan: TrainingPlan, evidence: EvidenceReader, control: OperationControl
) -> LoadedDataset:
    receipt = original_document(
        plan.dataset.export_receipt_ref, ExportReceipt, evidence, control
    )
    if receipt.dataset_ref is None:
        raise EvidenceIntegrityError("Empty export cannot enter training worker")
    manifest = original_document(
        receipt.dataset_ref, DatasetManifest, evidence, control
    )
    examples = tuple(
        original_document(item.example_ref, TrainingExample, evidence, control)
        for item in manifest.items
    )
    result = LoadedDataset(receipt, manifest, examples, plan.dataset.purpose)
    require_training_dataset(plan, result)
    return result
