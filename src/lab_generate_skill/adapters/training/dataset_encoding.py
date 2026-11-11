"""Original common SFT encoder over the single validated example schema."""

from typing import Any
from lab_generate_skill.domain.dataset import TrainingExample
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from .supervised_encoding import encode_supervised_record


def supervised_record(example: TrainingExample) -> dict[str, Any]:
    example = TrainingExample.model_validate(example)
    return {
        "id": example.legacy_id,
        "task_id": example.task.task_id,
        "task_type": example.task.site,
        "goal_group_id": example.goal_group_id,
        "messages": [m.model_dump() for m in example.messages],
        "metadata": example.labels.model_dump(),
    }


def encode_loaded_dataset(
    data: LoadedDataset,
    tokenizer: Any,
    *,
    max_seq_length: int,
    control: OperationControl,
) -> tuple[dict[str, Any], ...]:
    if type(max_seq_length) is not int or not 0 < max_seq_length <= 40960:
        raise ValueError("Explicit original Generator/SFT sequence budget required")
    if data.purpose == "sft" and (
        data.receipt.kind != "formal"
        or data.manifest is None
        or data.manifest.status != "train_validation_ready"
    ):
        raise EvidenceIntegrityError(
            "Fixture, empty or accumulation exports cannot start SFT"
        )
    result = []
    for example in data.examples:
        control.checkpoint()
        result.append(
            encode_supervised_record(
                tokenizer, supervised_record(example), max_seq_length=max_seq_length
            )
        )
        control.checkpoint()
    return tuple(result)
