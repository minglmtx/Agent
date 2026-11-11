"""Actual CAS/journal/file chain with explicit synthetic model/kernel/authority."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.training.sft import (
    OriginalSFTTrainer,
    TrainingBackendUnconfirmed,
)
from lab_generate_skill.adapters.training.resource import (
    RegisteredTrainingResource,
    TrainingResourceUnconfirmed,
)
from lab_generate_skill.adapters.training.closed_authority import (
    ClosedTrainingWorkerAuthority,
)
from lab_generate_skill.adapters.training.inputs import build_sft_inputs
from lab_generate_skill.adapters.training.resource_records import phase, metadata
from lab_generate_skill.adapters.training.output_store import checkpoint_metadata
from lab_generate_skill.domain.training_output import (
    SFTCheckpoint,
    NativeTrainingExecution,
)
from lab_generate_skill.domain.training import TrainingRunResult
from lab_generate_skill.adapters.training.recorded_runtime import (
    RecordedTrainingRuntime,
)
from lab_generate_skill.domain.training_resource import (
    TrainingResourceSpec,
    TrainingLaunch,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    DispatchAlreadyCommitted,
    RevisionConflict,
    EvidenceIntegrityError,
)
from lab_generate_skill.domain.lifecycle import OperationContext, ResourceRecord
from lab_generate_skill.ports.lifecycle import OperationControl
from training_resource_fixtures import TrainingResourceCase, unit_case
from test_slurm_commands import guard


@pytest.fixture
def c(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TrainingResourceCase:
    return unit_case(tmp_path, monkeypatch)


def train(c: TrainingResourceCase) -> tuple[TrainingRunResult, RecordedTrainingRuntime]:
    runtime = c.runtime()
    plan = c.spec.configuration.output.training
    trainer = OriginalSFTTrainer(
        Path(c.spec.configuration.output.output_root).parent,
        runtime,
        c.controls,
        c.clock,
    )
    return (
        trainer.train(plan, c.c.source.data, c.controls.bind(plan.dataset.operation)),
        runtime,
    )


def test_original_entry_registered_once_native_output_closed_and_independent_bytes(
    c: TrainingResourceCase,
) -> None:
    result, runtime = train(c)
    assert result.status == "completed" and result.optimizer_steps == 1
    assert len(c.channels) == len(c.cores) == 1 and c.channels[0].starts == 1
    assert [json.loads(v)["operation"] for v in c.channels[0].sent] == [
        "configure",
        "train",
        "close",
    ]
    spec = c.spec
    op = spec.operation.cleanup(
        "unit-read-after-close", now=datetime.now(timezone.utc), seconds=30
    )
    record = c.journal.read(spec.configuration.token, op)
    assert [e.state for e in record.events] == [
        "registered",
        "acquiring",
        "acquired",
        "closing",
        "closed",
    ]
    intent = json.loads(c.c.store.read(record.events[1].evidence[0]))
    launch = TrainingLaunch.model_validate_json(
        c.c.store.read(EvidenceRef.model_validate(intent["configuration_ref"]))
    )
    assert c.c.store.read(launch.command_ref) == c.channels[0].sent[1]
    snapshot = runtime.checkpoints.read(result.checkpoint_ref, c.c.source.data, guard())
    assert (
        snapshot.plan == spec.configuration.output
        and snapshot.closure.status == "closed"
    )
    assert (
        snapshot.closure.primary_error is None and not snapshot.closure.cleanup_errors
    )
    assert snapshot.artifact.files == snapshot.source.files
    # A new object/session still cannot pass the original durable acquisition.
    other = RegisteredTrainingResource(
        launch,
        journal=c.journal,
        evidence=c.c.store,
        controls=c.controls,
        clock=c.clock,
        authority=c.authority,
        allocation_verifier=c.allocator,
    )
    with pytest.raises((DispatchAlreadyCommitted, RevisionConflict, OwnershipConflict)):
        other.start(guard())
    assert len(c.cores) == 1 and sum(v.starts for v in c.channels) == 1


@pytest.mark.parametrize(
    "phase_name", ["source", "start", "started", "training", "closed"]
)
def test_denied_actual_gate_never_fabricates_training_or_clean_close(
    c: TrainingResourceCase, phase_name: str
) -> None:
    if phase_name == "source":
        c.source_authority.denied = True
    else:
        c.authority.denied = phase_name
    with pytest.raises(TrainingBackendUnconfirmed) as error:
        train(c)
    assert error.value.primary is not None
    if phase_name in ("source", "start"):
        assert not c.channels and not c.cores
    elif phase_name in ("started", "training"):
        assert c.channels[0].capture.termination is not None and not c.cores
    else:
        assert len(c.cores) == 1 and c.channels[0].capture.termination is not None
        assert error.value.cleanup_errors


@pytest.mark.parametrize("when", ["before", "after"])
def test_unknown_begin_acquire_never_starts_or_cleans_foreign_worker(
    c: TrainingResourceCase, monkeypatch: pytest.MonkeyPatch, when: str
) -> None:
    original = c.journal.begin_acquire
    failure = OSError("unit acquisition acknowledgement unknown")

    def lose(
        token: Any, ref: EvidenceRef, revision: int, op: OperationContext
    ) -> ResourceRecord:
        if when == "after":
            original(token, ref, revision, op)
        raise failure

    monkeypatch.setattr(c.journal, "begin_acquire", lose)
    with pytest.raises(TrainingBackendUnconfirmed) as error:
        train(c)
    assert (
        error.value.primary is failure
        and c.channels[0].starts == c.channels[0].aborts == 0
    )
    assert not c.cores and not Path(c.spec.configuration.output.output_root).exists()


@pytest.mark.parametrize("when", ["before", "after"])
def test_unknown_start_retains_quarantine_and_never_trains(
    c: TrainingResourceCase, monkeypatch: pytest.MonkeyPatch, when: str
) -> None:
    from training_resource_fixtures import UnitOwnedChannel

    original = UnitOwnedChannel.start

    def lose(self: UnitOwnedChannel, control: OperationControl) -> None:
        self.start_failure = when
        original(self, control)

    monkeypatch.setattr(UnitOwnedChannel, "start", lose)
    with pytest.raises(TrainingBackendUnconfirmed):
        train(c)
    assert c.channels[0].starts == 1 and c.channels[0].aborts == 1 and not c.cores
    op = c.spec.operation.cleanup(
        "unit-unknown-start-read", now=datetime.now(timezone.utc), seconds=30
    )
    assert c.journal.read(c.spec.configuration.token, op).state == "quarantined"


def test_unknown_training_reply_keeps_exact_intent_and_no_second_core(
    c: TrainingResourceCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    from training_resource_fixtures import UnitOwnedChannel

    original = UnitOwnedChannel.exchange

    def lose(self: UnitOwnedChannel, raw: bytes, control: OperationControl) -> bytes:
        self.lose_reply = json.loads(raw)["operation"] == "train"
        return original(self, raw, control)

    monkeypatch.setattr(UnitOwnedChannel, "exchange", lose)
    with pytest.raises(TrainingBackendUnconfirmed):
        train(c)
    assert len(c.cores) == 1
    op = c.spec.operation.cleanup(
        "unit-unknown-return-read", now=datetime.now(timezone.utc), seconds=30
    )
    record = c.journal.read(c.spec.configuration.token, op)
    intent = json.loads(c.c.store.read(record.events[1].evidence[0]))
    launch = TrainingLaunch.model_validate_json(
        c.c.store.read(EvidenceRef.model_validate(intent["configuration_ref"]))
    )
    assert c.c.store.read(launch.command_ref) == c.channels[0].sent[1]
    assert (
        len([x for x in c.channels[0].sent if json.loads(x)["operation"] == "train"])
        == 1
    )


@pytest.mark.parametrize("state_name", ["closing", "closed"])
def test_bookkeeping_lost_ack_cannot_skip_physical_close_or_invent_snapshot(
    c: TrainingResourceCase, monkeypatch: pytest.MonkeyPatch, state_name: str
) -> None:
    original = c.journal.advance

    def lose(
        token: Any,
        state: Any,
        refs: tuple[EvidenceRef, ...],
        revision: int,
        op: OperationContext,
    ) -> ResourceRecord:
        result = original(token, state, refs, revision, op)
        if state == state_name:
            raise OSError("unit journal acknowledgement lost")
        return result

    monkeypatch.setattr(c.journal, "advance", lose)
    with pytest.raises(TrainingBackendUnconfirmed):
        train(c)
    assert len(c.cores) == 1 and c.channels[0].capture.termination is not None
    assert c.channels[0].capture.termination.state == "reaped"
    assert not list(Path(c.spec.configuration.output.publication_root).iterdir())


@pytest.mark.parametrize(
    "fault", ["allocation", "deadline", "wrong-role", "wrong-argv", "extra"]
)
def test_resource_scope_schema_and_wrong_type_fail_before_events(
    c: TrainingResourceCase, fault: str
) -> None:
    raw = c.spec.model_dump()
    if fault == "allocation":
        raw["operation"]["allocation_id"] = "other"
    elif fault == "deadline":
        raw["operation"]["deadline"] = raw["operation"]["deadline"].replace(year=2099)
    elif fault == "wrong-role":
        raw["configuration"]["token"]["resource_kind"] = "actor"
    elif fault == "wrong-argv":
        raw["slurm"]["srun_executable"] = ""
    else:
        raw["legacy_fallback"] = True
    with pytest.raises(ValueError):
        TrainingResourceSpec.model_validate(raw)
    assert not c.channels and not list(c.journal._root.iterdir())


def test_closed_output_reader_rejects_wrong_native_identity_or_read_permission(
    c: TrainingResourceCase,
) -> None:
    result, runtime = train(c)
    snapshot = runtime.checkpoints.read(result.checkpoint_ref, c.c.source.data, guard())
    native = NativeTrainingExecution.model_validate_json(
        c.c.store.read(snapshot.execution_ref)
    )
    authority = ClosedTrainingWorkerAuthority(c.spec, c.c.store, c.authority)
    authority.verify_closed(
        snapshot.plan, c.c.source.data, native, snapshot.closure, "read", guard()
    )
    c.authority.denied = "read"
    with pytest.raises(PermissionError):
        authority.verify_closed(
            snapshot.plan, c.c.source.data, native, snapshot.closure, "read", guard()
        )
    c.authority.denied = None
    wrong = native.model_copy(
        update={
            "worker": native.worker.model_copy(
                update={"start_ticks": native.worker.start_ticks + 1}
            )
        }
    )
    with pytest.raises(EvidenceIntegrityError):
        authority.verify_closed(
            snapshot.plan, c.c.source.data, wrong, snapshot.closure, "read", guard()
        )


def test_cancel_before_train_uses_independent_close_without_native_dispatch(
    c: TrainingResourceCase,
) -> None:
    class Stopped:
        def checkpoint(self) -> float:
            raise InterruptedError("unit original training cancelled")

        def wait(self, seconds: float) -> None:
            raise InterruptedError("unit original training cancelled")

    runtime = c.runtime()
    plan = c.spec.configuration.output.training
    output = Path(c.spec.configuration.output.output_root)
    runtime.verify(plan, c.c.source.data, output, guard())
    contract = build_sft_inputs(plan, c.c.source.data, output).contract
    failure = InterruptedError("unit original training cancelled")
    with pytest.raises(InterruptedError):
        runtime.execute(plan, c.c.source.data, output, contract, Stopped())
    runtime.abort(plan, c.c.source.data, output, failure, guard(30))
    assert not c.cores and not output.exists()
    assert [json.loads(v)["operation"] for v in c.channels[0].sent] == [
        "configure",
        "close",
    ]


@pytest.mark.parametrize(
    "schema",
    [
        "sft-worker-command/1",
        "sft-training-launch/1",
        "sft-resource-acquired/1",
        "train-reply",
    ],
)
@pytest.mark.parametrize("after", [False, True])
def test_partial_evidence_publication_retains_original_ref_and_never_reexecutes(
    c: TrainingResourceCase, monkeypatch: pytest.MonkeyPatch, schema: str, after: bool
) -> None:
    original = c.c.store.put
    failure = OSError("unit exact publication acknowledgement unknown")
    injected = False

    def lose(
        raw: bytes,
        meta: EvidenceMetadata,
        control: OperationControl | None = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        nonlocal injected
        match = meta.content_schema == schema
        if schema == "train-reply":
            match = (
                meta.content_schema == "sft-worker-reply/1"
                and json.loads(raw)["operation"] == "train"
            )
        if match and not injected:
            injected = True
            if after:
                original(raw, meta, control, exchange_id=exchange_id)
            raise failure
        return original(raw, meta, control, exchange_id=exchange_id)

    monkeypatch.setattr(c.c.store, "put", lose)
    with pytest.raises(TrainingBackendUnconfirmed) as error:
        train(c)
    assert injected and getattr(failure, "training_resource_reference") is not None
    assert error.value.primary is not None
    assert len(c.cores) == (1 if schema == "train-reply" else 0)
    assert sum(v.starts for v in c.channels) == (
        1 if schema in ("sft-resource-acquired/1", "train-reply") else 0
    )
    assert not list(Path(c.spec.configuration.output.publication_root).iterdir())
