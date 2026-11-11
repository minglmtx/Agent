"""Original native return and complete-file gates; no fake task/model success."""

from dataclasses import replace
from pathlib import Path
from typing import Any
import json
import os
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.training_output import TrainingOutputPlan, SFTCheckpoint
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OperationStopped,
    InvalidTransition,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.training.output_store import (
    CheckpointPublicationUnconfirmed,
    checkpoint_metadata,
)
from lab_generate_skill.adapters.training.files import atomic_json
from lab_generate_skill.adapters.training.native_execution import (
    native_metadata,
    NativeReturnCommitUnconfirmed,
)
from lab_generate_skill.adapters.training.recorded_runtime import (
    RecordedTrainingRuntime,
)
from training_entry_fixtures import training_case, TrainingCase
from training_output_fixtures import output_case
from test_training_output import UnitFileExecution


@pytest.mark.parametrize(
    "change",
    [
        {"max_files": 0},
        {"max_files": True},
        {"max_file_bytes": 0},
        {"max_total_bytes": -1},
        {"workspace_root": "relative"},
        {"publication_root": None},
        {"unknown": True},
    ],
)
def test_output_plan_rejects_wrong_empty_illegal_and_unbounded_fields(
    training_case: TrainingCase, change: dict[str, Any]
) -> None:
    c = output_case(training_case, "illegal", create_files=False)
    with pytest.raises(ValidationError):
        TrainingOutputPlan.model_validate({**c.plan.model_dump(), **change})


def test_native_capture_denied_before_any_output_filesystem_read(
    training_case: TrainingCase,
) -> None:
    c = output_case(training_case, "denied-before-read", create_files=False)
    c.worker_authority.denied = True
    before = len(c.store.put_sizes)
    with pytest.raises(PermissionError):
        c.returned()  # source directory deliberately does not exist
    assert not Path(c.plan.output_root).exists() and len(c.store.put_sizes) == before


def test_parent_rights_revoked_or_closure_unconfirmed_has_no_snapshot(
    training_case: TrainingCase,
) -> None:
    c = output_case(training_case, "close-denied")
    returned = c.returned()
    c.worker_authority.denied = True
    with pytest.raises(CheckpointPublicationUnconfirmed) as caught:
        c.checkpoints().publish(c.plan, c.data, c.closure, returned, c.control())
    assert (
        isinstance(caught.value.primary, PermissionError)
        and caught.value.artifact is None
        and caught.value.reference is None
    )
    assert list(Path(c.plan.publication_root).iterdir()) == []
    c.worker_authority.denied = False
    unknown = c.closure.model_copy(update={"status": "unconfirmed"})
    with pytest.raises(ValueError, match="complete trainer resource closure"):
        c.checkpoints().publish(c.plan, c.data, unknown, returned, c.control())
    assert list(Path(c.plan.publication_root).iterdir()) == []


@pytest.mark.parametrize("fault", ["last-byte", "new-file", "non-target-config"])
def test_changes_after_original_return_are_not_moved_into_new_baseline(
    training_case: TrainingCase, fault: str
) -> None:
    c = output_case(training_case, "changed-" + fault)
    returned = c.returned()
    root = Path(c.plan.output_root)
    if fault == "last-byte":
        file = root / "checkpoint-000001/training_state.pt"
        with file.open("r+b") as stream:
            stream.seek(-1, 2)
            stream.write(b"X")
    elif fault == "new-file":
        (root / "unexpected-extra.bin").write_bytes(b"must not disappear")
    else:
        (root / "tokenizer/tokenizer_config.json").write_text('{"changed":true}')
    with pytest.raises(CheckpointPublicationUnconfirmed) as caught:
        c.checkpoints().publish(c.plan, c.data, c.closure, returned, c.control())
    assert isinstance(
        caught.value.primary, EvidenceIntegrityError
    ) and "after original" in str(caught.value.primary)
    assert caught.value.reference is None and caught.value.artifact is None
    assert list(Path(c.plan.publication_root).iterdir()) == []


@pytest.mark.parametrize(
    "fault",
    [
        "missing-state",
        "incomplete-marker",
        "wrong-contract",
        "wrong-step",
        "unknown-config-field",
        "duplicate-summary-key",
        "nonfinite-summary",
    ],
)
def test_original_invalid_native_material_is_preserved_and_never_becomes_training_result(
    training_case: TrainingCase, fault: str
) -> None:
    c = output_case(training_case, "bad-native-" + fault)
    root = Path(c.plan.output_root)
    if fault == "missing-state":
        (root / "checkpoint-000001/training_state.pt").unlink()
    elif fault == "incomplete-marker":
        atomic_json(
            root / "checkpoint-000001/complete.json", {"complete": False, "step": 1}
        )
    elif fault == "wrong-contract":
        raw = json.loads((root / "run_manifest.json").read_text())
        raw["training_id"] = "wrong"
        atomic_json(root / "run_manifest.json", raw)
    elif fault == "wrong-step":
        raw = json.loads((root / "training_config.json").read_text())
        raw["planned_optimizer_steps"] = 2
        atomic_json(root / "training_config.json", raw)
    elif fault == "unknown-config-field":
        raw = json.loads((root / "training_config.json").read_text())
        raw["silently_ignore_me"] = True
        atomic_json(root / "training_config.json", raw)
    elif fault == "duplicate-summary-key":
        (root / "training_summary.json").write_text('{"complete":true,"complete":true}')
    else:
        (root / "training_summary.json").write_text(
            '{"complete":true,"elapsed_seconds":NaN}'
        )
    returned = c.returned()
    with pytest.raises(CheckpointPublicationUnconfirmed) as caught:
        c.checkpoints().publish(c.plan, c.data, c.closure, returned, c.control())
    assert (
        caught.value.phase == "native_contract_and_checkpoint"
        and caught.value.reference is None
    )
    assert caught.value.artifact is not None and root.exists()
    # The raw invalid original artifact is preserved, with no success metadata.
    assert len(list(Path(c.plan.publication_root).iterdir())) == 1


def test_stopped_known_native_result_preserves_complete_checkpoint_without_final_adapter(
    training_case: TrainingCase,
) -> None:
    c = output_case(training_case, "stopped", completed=False)
    returned = c.returned()
    ref = c.checkpoints().publish(c.plan, c.data, c.closure, returned, c.control())
    snap = c.checkpoints().read(ref, c.data, c.control())
    assert (
        snap.native.status == "stopped"
        and snap.native.optimizer_steps == 1
        and snap.native.planned_optimizer_steps == 2
    )
    assert not any(f.path.startswith("final_adapter/") for f in snap.artifact.files)


def test_forged_stored_outcome_and_corrupt_published_tail_fail_independent_read(
    training_case: TrainingCase,
) -> None:
    c = output_case(training_case, "forged-outcome")
    returned = c.returned()
    store = c.checkpoints()
    ref = store.publish(c.plan, c.data, c.closure, returned, c.control())
    snap = store.read(ref, c.data, c.control())
    forged = SFTCheckpoint.model_validate(
        {
            **snap.model_dump(),
            "native": snap.native.model_copy(update={"status": "stopped"}),
        }
    )
    fake = c.store.put(forged.model_dump_json().encode(), checkpoint_metadata())
    with pytest.raises(EvidenceIntegrityError, match="outcome differs"):
        store.read(fake, c.data, c.control())
    file = Path(snap.artifact.root) / "checkpoint-000001/training_state.pt"
    file.chmod(0o600)
    with file.open("r+b") as stream:
        stream.seek(-1, 2)
        stream.write(b"X")
    file.chmod(0o444)
    with pytest.raises(EvidenceIntegrityError):
        store.read(ref, c.data, c.control())


def test_partial_freeze_keeps_primary_candidate_and_never_recopies_unknown_target(
    training_case: TrainingCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = output_case(training_case, "partial-freeze")
    returned = c.returned()
    primary = OSError("unit second pinned member copy failed")
    from lab_generate_skill.adapters.releases import artifact_freeze
    from lab_generate_skill.adapters.releases.artifact_copy import copy_pinned_file

    real = copy_pinned_file
    copied: list[str] = []

    def copy(*args: Any, **kwargs: Any) -> None:
        if copied:
            raise primary
        real(*args, **kwargs)
        copied.append("one")

    monkeypatch.setattr(artifact_freeze, "copy_pinned_file", copy)
    with pytest.raises(CheckpointPublicationUnconfirmed) as caught:
        c.checkpoints().publish(c.plan, c.data, c.closure, returned, c.control())
    assert (
        caught.value.primary is primary
        and caught.value.reference is None
        and caught.value.artifact is not None
    )
    targets = list(Path(c.plan.publication_root).iterdir())
    assert (
        len(targets) == 1 and targets[0].exists() and Path(c.plan.output_root).exists()
    )
    with pytest.raises(CheckpointPublicationUnconfirmed):
        c.checkpoints().publish(c.plan, c.data, c.closure, returned, c.control())
    assert copied == ["one"]


def test_lost_checkpoint_ack_is_resolved_by_original_reference_read_only(
    training_case: TrainingCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = output_case(training_case, "lost-ack")
    returned = c.returned()
    real = c.store.put
    error = OSError("unit checkpoint commit acknowledged late")

    def put(
        data: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
        **kwargs: Any,
    ) -> EvidenceRef:
        ref = real(data, metadata, control, **kwargs)
        if metadata.content_schema == "sft-checkpoint/1":
            raise error
        return ref

    monkeypatch.setattr(c.store, "put", put)
    with pytest.raises(CheckpointPublicationUnconfirmed) as caught:
        c.checkpoints().publish(c.plan, c.data, c.closure, returned, c.control())
    assert caught.value.primary is error and caught.value.reference is not None
    n = len(c.store.put_sizes)
    snap = c.checkpoints().read(caught.value.reference, c.data, c.control())
    assert snap.native.status == "completed" and len(c.store.put_sizes) == n


def test_unknown_native_execution_cannot_dispatch_again_or_claim_output(
    training_case: TrainingCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = output_case(training_case, "unknown", create_files=False)
    execution = UnitFileExecution(c)
    runtime = RecordedTrainingRuntime(
        c.workspace,
        Path(c.plan.publication_root),
        128,
        128 * 1024**2,
        512 * 1024**2,
        execution,
        c.checkpoints(),
    )
    control = c.control()
    from lab_generate_skill.adapters.training.inputs import build_sft_inputs

    request = build_sft_inputs(c.plan.training, c.data, Path(c.plan.output_root))
    runtime.verify(c.plan.training, c.data, Path(c.plan.output_root), control)
    primary = TimeoutError("unit original worker reply unknown")
    count = 0

    def unknown(*args: Any, **kwargs: Any) -> EvidenceRef:
        nonlocal count
        count += 1
        raise primary

    monkeypatch.setattr(execution, "execute", unknown)
    with pytest.raises(TimeoutError) as caught:
        runtime.execute(
            c.plan.training, c.data, Path(c.plan.output_root), request.contract, control
        )
    assert caught.value is primary
    with pytest.raises(InvalidTransition, match="execute once"):
        runtime.execute(
            c.plan.training, c.data, Path(c.plan.output_root), request.contract, control
        )
    with pytest.raises(InvalidTransition, match="Unknown/unreturned"):
        runtime.finish(
            c.plan.training, c.data, Path(c.plan.output_root), request.contract, control
        )
    assert (
        count == 1 and runtime.execution_ref is None and runtime.checkpoint_ref is None
    )


def test_empty_original_output_is_not_a_valid_empty_training_result(
    training_case: TrainingCase,
) -> None:
    c = output_case(training_case, "empty-output", create_files=False)
    Path(c.plan.output_root).mkdir(mode=0o700)
    n = len(c.store.put_sizes)
    with pytest.raises(EvidenceIntegrityError, match="file set"):
        c.returned()
    assert len(c.store.put_sizes) == n


def test_cancel_during_original_pin_preserves_sources_without_publication(
    training_case: TrainingCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = output_case(training_case, "cancel-pin")
    returned = c.returned()
    primary = OperationStopped(
        "CANCELLED", c.plan.training.dataset.operation.operation_id
    )
    real = os.read
    reads: list[int] = []

    def interrupted(fd: int, count: int) -> bytes:
        raw = real(fd, count)
        reads.append(len(raw))
        raise primary

    monkeypatch.setattr(os, "read", interrupted)
    with pytest.raises(CheckpointPublicationUnconfirmed) as caught:
        c.checkpoints().publish(c.plan, c.data, c.closure, returned, c.control())
    assert (
        caught.value.primary is primary
        and caught.value.phase == "complete_native_output_pin"
    )
    assert reads and caught.value.reference is None and caught.value.artifact is None
    assert (
        Path(c.plan.output_root).exists()
        and list(Path(c.plan.publication_root).iterdir()) == []
    )
