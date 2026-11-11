"""Independent real consumers of retained output; no historical continuation.

Every test opens the original CAS read-only. Output manifests are engineering
diagnostics; they never acquire an owner/claim, register an action or qualify SFT.
"""

from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.models.actor_execution_evidence import verify_execution
from lab_generate_skill.adapters.models.local_actor_evidence import ActorEvidence
from lab_generate_skill.adapters.plans.baseline_evidence import BaselineEvidenceReader
from lab_generate_skill.adapters.plans.reset_evidence import ResetEvidenceReader
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.application.actor_loop_inputs import public_turn
from lab_generate_skill.bootstrap.actor_context_review import closed_actor_context
from lab_generate_skill.domain.baseline import BaselineReceipt
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.local_actor import LocalActorExecution
from lab_generate_skill.domain.reset import ResetReceipt
from lab_generate_skill.domain.task_execution import InitializedTask
from lab_generate_skill.domain.trace_events import GenerationPlanned
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.runtime.lifecycle import OperationGuards
from source_review_records import ReadOnlyEvidence

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
C = W / "experiments/framework-combined-release-20261030-v1"
D = C / "frozen-stage-discovery-4961650"
CASES = [("map", "4960645"), ("admin", "4949938"), ("admin", "4955553")]


class OfflineCancellation:
    def is_cancelled(self, reference: Any) -> bool:
        raise AssertionError("Offline review must not use an old live control channel")


class CountedReadOnly(ReadOnlyEvidence):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.reads: Counter[EvidenceRef] = Counter()

    def read(self, reference: EvidenceRef, control: Any) -> bytes:
        self.reads[reference] += 1
        return super().read(reference, control)


@pytest.fixture(params=CASES, ids=[s + "-" + j for s, j in CASES])
def retained(request: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    from lab_generate_skill.adapters.sites.task_preparation import (
        RecordedSiteTaskPreparation,
    )
    from lab_generate_skill.adapters.sites.task_initialization import (
        RecordedTaskInitialization,
    )
    from lab_generate_skill.adapters.models.local_actor import RecordedLocalActorModel
    import lab_generate_skill.bootstrap.source_qualification_measurement as source

    calls: Counter[str] = Counter()

    def forbidden(label: str) -> Any:
        def fail(*args: Any, **kwargs: Any) -> Any:
            calls[label] += 1
            pytest.fail("Frozen consumer called upstream producer: " + label)

        return fail

    monkeypatch.setattr(source, "measure_source", forbidden("source"))
    monkeypatch.setattr(RecordedSiteTaskPreparation, "acquire", forbidden("acquire"))
    monkeypatch.setattr(RecordedSiteTaskPreparation, "prepare", forbidden("prepare"))
    monkeypatch.setattr(RecordedTaskInitialization, "start", forbidden("initialize"))
    monkeypatch.setattr(RecordedLocalActorModel, "generate", forbidden("model"))
    site, job = request.param
    index = json.loads((D / (site + "-" + job + "-outputs.json")).read_bytes())
    root = Path(index["root"])
    controls = OperationGuards(SystemClock(), OfflineCancellation())
    store = CountedReadOnly(root / "evidence")
    refs = [
        EvidenceRef.model_validate(r["reference"])
        for r in index["references"]
        if r["verified_reads"] == 1
    ]
    initialized_refs = [r for r in refs if r.content_schema == "initialized-task/1"]
    assert len(initialized_refs) == 1
    from lab_generate_skill.adapters.processes.deadline import DeadlineControl

    initial = InitializedTask.model_validate_json(
        store.read(initialized_refs[0], DeadlineControl(120, "offline-input-open"))
    )
    scope = initial.actor.scope
    operation = OperationContext(
        operation_id="independent-frozen-consumer",
        run_id=scope.owner.run_id,
        owner_id=scope.owner.owner_id,
        attempt_id=scope.attempt_id,
        mode="cleanup",
        parent_operation_id=initial.actor.operation.operation_id,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=120),
    )
    case = dict(
        site=site,
        job=job,
        root=root,
        refs=refs,
        initial=initial,
        operation=operation,
        controls=controls,
        store=store,
        calls=calls,
        initialized_ref=initialized_refs[0],
    )
    yield case
    assert not calls
    out = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    key = site + "-" + job + "-" + request.node.originalname
    (out / (key + ".json")).write_text(
        json.dumps(
            dict(
                evidence_mode="original-retained-read-only; diagnostic-derived-output",
                original_job=job,
                original_initialized_ref=initialized_refs[0].model_dump(mode="json"),
                upstream_calls=dict(calls),
                upstream_total_calls=sum(calls.values()),
                body_reads=sum(store.reads.values()),
                distinct_full_references=len(store.reads),
                repeated_body_reads=sum(n - 1 for n in store.reads.values()),
                original_evidence_or_ledger_writes=0,
                runtime_or_training_grant=False,
                outputs=case.get("outputs", []),
            ),
            indent=2,
        )
        + "\n"
    )


def test_S3_baseline_output_is_directly_consumed_by_S4_public_turn(
    retained: Any,
) -> None:
    c = retained
    store, initial = c["store"], c["initial"]
    control = c["controls"].bind(c["operation"])
    baseline = StateReads(store).parse(
        initial.baseline_ref,
        "baseline-receipt/1",
        BaselineReceipt,
        control,
        expected_reference=initial.baseline_ref,
    )
    inputs = BaselineEvidenceReader(store).verify(baseline, control)
    assert inputs.observation_ref == initial.actor.initial_observation_ref
    assert inputs.public_task == initial.actor.task and baseline.status == "ready"
    paths = list((c["root"] / "trace").glob("*.trace.json"))
    assert len(paths) == 1
    snapshot = TraceSnapshot.model_validate_json(paths[0].read_bytes())
    prefix = TraceSnapshot.model_validate(snapshot.model_copy(update={"events": ()}))
    turn = public_turn(
        initial.actor,
        prefix,
        c["operation"],
        control,
        store,
        EvidenceObservations(store, c["controls"]),
    )
    assert turn.observation.record == inputs.observation
    assert turn.task == inputs.public_task
    c["outputs"] = [
        dict(
            stage="S3",
            reference=initial.baseline_ref.model_dump(mode="json"),
            consumer="BaselineEvidenceReader.verify -> public_turn",
            next_input_ref=inputs.observation_ref.model_dump(mode="json"),
            serialized_public_turn=turn.model_dump(mode="json"),
        )
    ]


def test_S6_retained_execution_and_S4_original_context_without_inference(
    retained: Any,
) -> None:
    c = retained
    executions = tuple(
        LocalActorExecution.model_validate_json(
            c["store"].read(ref, c["controls"].bind(c["operation"]))
        )
        for ref in c["refs"]
        if ref.content_schema == "local-actor-execution/1"
    )
    if c["job"] == "4949938":
        assert executions == ()
        c["outputs"] = [
            dict(
                stage="S6",
                result="original_response_present_but_no_LocalActorExecution; no synthetic_registration",
                next="reuse original raw-return review; fault/partial branch only",
            )
        ]
        return
    assert len(executions) == (2 if c["site"] == "map" else 1)
    control = c["controls"].bind(c["operation"])
    snapshot_paths = list((c["root"] / "trace").glob("*.trace.json"))
    assert len(snapshot_paths) == 1
    snapshot = TraceSnapshot.model_validate_json(snapshot_paths[0].read_bytes())
    request = c["initial"].actor
    reviewer = closed_actor_context(
        request,
        executions,
        c["store"],
        EvidenceObservations(c["store"], c["controls"]),
        control=control,
    )
    outputs = []
    for execution in executions:
        verify_execution(ActorEvidence(c["store"]), execution, control)
        positions = [
            i
            for i, event in enumerate(snapshot.events)
            if isinstance(event, GenerationPlanned)
            and event.intent == execution.call.intent
        ]
        assert len(positions) == 1
        prefix = TraceSnapshot.model_validate(
            snapshot.model_copy(update={"events": snapshot.events[: positions[0]]})
        )
        prompt = reviewer.verify(
            request, prefix, execution.call.intent, c["operation"], control=control
        )
        assert prompt.model_dump_json().encode() == c["store"].read(
            execution.call.intent.input_ref, control
        )
        outputs.append(
            dict(
                stage="S4/S6",
                consumer="closed_actor_context.verify + verify_execution",
                original_input_ref=execution.call.intent.input_ref.model_dump(
                    mode="json"
                ),
                response_ref=execution.response_ref.model_dump(mode="json"),
            )
        )
    c["outputs"] = outputs


def test_S9_original_reset_dependencies_are_read_only(retained: Any) -> None:
    c = retained
    refs = [ref for ref in c["refs"] if ref.content_schema == "reset-receipt/1"]
    assert refs
    control = c["controls"].bind(c["operation"])
    outputs = []
    for ref in refs:
        reset = StateReads(c["store"]).parse(
            ref, "reset-receipt/1", ResetReceipt, control
        )
        inputs = ResetEvidenceReader(c["store"]).verify(reset, control)
        assert inputs.plan.scope == reset.scope
        outputs.append(
            dict(
                stage="S9",
                reference=ref.model_dump(mode="json"),
                consumer="ResetEvidenceReader.verify",
                original_scope=reset.scope.model_dump(mode="json"),
                status=reset.status,
                task_close_proven=False,
            )
        )
    c["outputs"] = outputs


@pytest.mark.parametrize(
    "fault", ["schema", "producer", "digest", "size", "visibility"]
)
def test_S3_bad_reference_refuses_without_prefix_reconstruction(
    retained: Any, fault: str
) -> None:
    c = retained
    ref = c["initial"].baseline_ref
    changes = dict(
        schema={"content_schema": "foreign/1"},
        producer={"producer": "foreign"},
        digest={"sha256": "f" * 64, "uri": "cas://sha256/" + "f" * 64},
        size={"size_bytes": ref.size_bytes + 1},
        visibility={"visibility": "public"},
    )
    bad = EvidenceRef.model_validate(ref.model_copy(update=changes[fault]))
    with pytest.raises(
        (ValueError, EvidenceIntegrityError, EvidenceNotFound, OwnershipConflict)
    ):
        StateReads(c["store"]).parse(
            bad,
            "baseline-receipt/1",
            BaselineReceipt,
            c["controls"].bind(c["operation"]),
            expected_reference=ref,
        )
    assert not c["calls"]


@pytest.mark.parametrize("bad", [None, "", {}, [], True, 1])
def test_S3_empty_or_wrong_reference_type_has_no_read_or_prefix(
    retained: Any, bad: Any
) -> None:
    c = retained
    before = sum(c["store"].reads.values())
    with pytest.raises(ValueError):
        StateReads(c["store"]).parse(
            bad,
            "baseline-receipt/1",
            BaselineReceipt,
            c["controls"].bind(c["operation"]),
            expected_reference=c["initial"].baseline_ref,
        )
    assert sum(c["store"].reads.values()) == before
    assert not c["calls"]


def test_S4_foreign_attempt_refuses_and_repeated_public_projection_is_stable(
    retained: Any,
) -> None:
    c = retained
    paths = list((c["root"] / "trace").glob("*.trace.json"))
    assert len(paths) == 1
    snapshot = TraceSnapshot.model_validate_json(paths[0].read_bytes())
    prefix = TraceSnapshot.model_validate(snapshot.model_copy(update={"events": ()}))
    request = c["initial"].actor
    operation, control = c["operation"], c["controls"].bind(c["operation"])
    observations = EvidenceObservations(c["store"], c["controls"])
    first = public_turn(request, prefix, operation, control, c["store"], observations)
    assert (
        public_turn(request, prefix, operation, control, c["store"], observations)
        == first
    )
    foreign = request.model_copy(
        update={"scope": request.scope.model_copy(update={"attempt_id": "foreign"})}
    )
    with pytest.raises(OwnershipConflict):
        public_turn(foreign, prefix, operation, control, c["store"], observations)
    assert not c["calls"]
