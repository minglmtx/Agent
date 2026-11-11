"""Native-return acknowledgement and original resource/role boundaries."""

import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.adapters.training.inputs import build_sft_inputs
from lab_generate_skill.adapters.training.native_execution import (
    native_metadata,
    NativeReturnCommitUnconfirmed,
)
from lab_generate_skill.adapters.training.output_store import (
    CheckpointPublicationUnconfirmed,
)
from lab_generate_skill.adapters.training.recorded_runtime import (
    RecordedTrainingRuntime,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from training_entry_fixtures import training_case, TrainingCase
from training_output_fixtures import output_case
from test_training_output import UnitFileExecution


def test_native_return_commit_with_lost_ack_keeps_original_candidate_no_reexecution(
    training_case: TrainingCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = output_case(training_case, "return-lost-ack")
    real = c.store.put
    error = OSError("unit original worker return committed, ack lost")

    def put(
        data: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
        **kwargs: Any,
    ) -> EvidenceRef:
        ref = real(data, metadata, control, **kwargs)
        if metadata.content_schema == "sft-native-execution/1":
            raise error
        return ref

    monkeypatch.setattr(c.store, "put", put)
    with pytest.raises(NativeReturnCommitUnconfirmed) as caught:
        c.returned()
    assert (
        caught.value.primary is error
        and caught.value.reference.content_schema == "sft-native-execution/1"
    )
    n = len(c.store.put_sizes)
    raw = c.store.read(caught.value.reference, c.control())
    assert (
        raw == caught.value.native.model_dump_json().encode()
        and len(c.store.put_sizes) == n
    )
    assert Path(c.plan.output_root).exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("returned", 1),
        ("training_id", "foreign-training"),
        ("schema_version", "sft-native-execution/0"),
    ],
)
def test_wrong_original_return_is_rejected_before_output_publication(
    training_case: TrainingCase, field: str, value: object
) -> None:
    c = output_case(training_case, "wrong-return-" + field)
    ref = c.returned()
    raw = json.loads(c.store.read(ref))
    raw[field] = value
    forged = c.store.put(json.dumps(raw).encode(), native_metadata())
    with pytest.raises(CheckpointPublicationUnconfirmed) as caught:
        c.checkpoints().publish(c.plan, c.data, c.closure, forged, c.control())
    assert caught.value.artifact is None and caught.value.reference is None
    assert list(Path(c.plan.publication_root).iterdir()) == []


def test_unconfirmed_close_retains_actual_fact_without_claiming_closed_or_snapshot(
    training_case: TrainingCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = output_case(training_case, "unconfirmed-close", create_files=False)
    e = UnitFileExecution(c)
    runtime = RecordedTrainingRuntime(
        c.workspace,
        Path(c.plan.publication_root),
        128,
        128 * 1024**2,
        512 * 1024**2,
        e,
        c.checkpoints(),
    )
    p = c.plan.training
    request = build_sft_inputs(p, c.data, Path(c.plan.output_root))
    runtime.verify(p, c.data, Path(c.plan.output_root), c.control())
    runtime.execute(p, c.data, Path(c.plan.output_root), request.contract, c.control())
    unknown = c.closure.model_copy(update={"status": "unconfirmed"})
    monkeypatch.setattr(e, "close", lambda *args: unknown)
    with pytest.raises(ValueError, match="complete trainer resource closure"):
        runtime.finish(
            p, c.data, Path(c.plan.output_root), request.contract, c.control()
        )
    assert runtime.last_closure == unknown and runtime.state == "closing"
    assert runtime.checkpoint_ref is None and runtime.execution_ref is not None
    assert list(Path(c.plan.publication_root).iterdir()) == []
