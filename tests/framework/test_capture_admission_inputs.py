"""Actual frozen Admin bodies; simulated current rights never grant old runtime.

Only capture admission is invoked. No source/start/Actor/browser/restore producer
runs, and the historical run prefix is represented solely in this test process.
"""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
import json
import os
from pathlib import Path
import threading
from types import SimpleNamespace
from typing import Any, Iterator, cast
import pytest
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.storage.readonly_evidence import ReadOnlyEvidence
from lab_generate_skill.adapters.plans.initial_observation import (
    InitialObservationReader,
)
from lab_generate_skill.adapters.sites.task_capture_admission_inputs import (
    TaskCaptureAdmissionInputs,
)
from lab_generate_skill.adapters.sites.task_capture_initial_reads import (
    TaskCaptureInitialReads,
)
from lab_generate_skill.adapters.sites.task_initialization import (
    RecordedTaskInitialization,
)
from lab_generate_skill.adapters.sites.task_initialization_state import (
    TaskInitializationState,
)
from lab_generate_skill.adapters.sites.task_initialization_inputs import (
    TaskInitializationInputs,
)
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.adapters.sites.task_preparation_inputs import (
    TaskPreparationDeclarationInputs,
)
from lab_generate_skill.application.task_capture_admission import TaskCaptureAuthority
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OwnershipConflict,
    RevisionConflict,
    OperationStopped,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.preparation import PreparedTask
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.task_capture import TaskCapturePlan, TaskCaptureInputs
from lab_generate_skill.domain.task_execution import TaskExecutionPlan, InitializedTask
from lab_generate_skill.domain.task_initialization import TaskInitializationPlan
from lab_generate_skill.domain.task_phase_source import TaskPhaseSourceState
from lab_generate_skill.domain.task_preparation import SiteTaskPreparationPlan
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.ports.task_preparation_inputs import PreparationDeclarationFacts
from lab_generate_skill.sites.shopping_admin.navigation_terminal_schema import (
    AdminNavigationTerminalSelection,
)

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
C = W / "experiments/framework-combined-release-20261030-v1"
INDEX = C / "finite-repair-results-4971353/admin-4971352-outputs.json"


@contextmanager
def case(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    assert os.environ.get("SLURM_JOB_ID")
    index = json.loads(INDEX.read_bytes())
    assert index["original_job"] == "4971352"
    control = DeadlineControl(120, "capture-admission-software-only")
    original = ReadOnlyEvidence(
        Path(index["root"]) / "evidence",
        max_object_bytes=64 * 1024**2,
        reuse_within_proof=True,
    )
    refs = [EvidenceRef.model_validate(row["reference"]) for row in index["references"]]

    def one(schema: str) -> EvidenceRef:
        selected = [ref for ref in refs if ref.content_schema == schema]
        assert len(selected) == 1
        return selected[0]

    def read(ref: EvidenceRef, model: Any) -> Any:
        return model.model_validate_json(original.read(ref, control))

    plan: TaskExecutionPlan = read(one("task-execution-plan/2"), TaskExecutionPlan)
    capture_ref = one("task-capture-plan/2")
    capture: TaskCapturePlan = read(capture_ref, TaskCapturePlan)
    prep: SiteTaskPreparationPlan = read(plan.declaration_ref, SiteTaskPreparationPlan)
    terminal_ref = one("admin-navigation-terminal-selection/1")
    terminal: AdminNavigationTerminalSelection = read(
        terminal_ref, AdminNavigationTerminalSelection
    )
    initialized: InitializedTask = read(one("initialized-task/1"), InitializedTask)
    initialization: TaskInitializationPlan = read(
        one("task-initialization-plan/2"), TaskInitializationPlan
    )

    class Prepared:
        def publish(self, *args: Any, **kwargs: Any) -> Any:
            raise AssertionError("No preparation publication")

        def load(self, publication: Any, operation: OperationContext) -> PreparedTask:
            result: PreparedTask = read(publication.prepared_ref, PreparedTask)
            assert result.scope == capture.scope
            assert (operation.run_id, operation.owner_id, operation.attempt_id) == (
                plan.operation.run_id,
                plan.operation.owner_id,
                plan.operation.attempt_id,
            )
            return result

    initial = InitialObservationReader(
        original, cast(PreparationRecords, Prepared())
    ).load(terminal.initial, plan.operation, control)
    facts = PreparationDeclarationFacts(
        prep,
        read(prep.site_spec_ref, SiteResourceSpec),
        read(plan.reset_plan_ref, ResetPlan),
        read(prep.task_binding_ref, TaskBinding),
    )

    class Current:
        denied = False
        calls = 0

        def check_context_current(
            self, operation: OperationContext, bounded: OperationControl
        ) -> None:
            bounded.checkpoint()
            self.calls += 1
            assert operation == plan.operation
            if self.denied:
                raise PermissionError("Original current context revoked")

    current = Current()
    scope = TaskInitializationInputs(plan)
    state = TaskInitializationState(
        phase="initialized", selection=initial.selection, result=initialized
    )
    producer = RecordedTaskInitialization.__new__(RecordedTaskInitialization)
    producer.plan, producer.inputs, producer.state = plan, scope, state
    producer.declaration, producer._current_initial = initialization, None
    producer.owner = os.getpid(), threading.get_ident()
    prepared = RecordedSiteTaskPreparation.__new__(RecordedSiteTaskPreparation)
    prepared.plan, prepared.declaration = plan, prep
    physical_reads: Counter[str] = Counter()

    class Original:
        def read(self, reference: EvidenceRef, bounded: OperationControl) -> bytes:
            physical_reads[reference.sha256] += 1
            return original.read(reference, bounded)

        def put(
            self, data: bytes, metadata: EvidenceMetadata, control: OperationControl
        ) -> EvidenceRef:
            raise AssertionError("Capture admission cannot publish")

    with scope.scope():
        declarations = TaskPreparationDeclarationInputs(plan, prep, scope, current)
        scope.preparation_declarations = declarations
        declarations.record(plan, facts, plan.operation, control)
        scope.initial = initial
        initials = TaskCaptureInitialReads(plan, scope, lambda: producer)
        reader = TaskCaptureAdmissionInputs(
            plan,
            capture,
            capture_ref,
            scope,
            prepared,
            lambda: producer,
            initials,
            Original(),
        )
        (trace_path,) = (INDEX.parent / "metadata/trace").glob("*.trace.json")
        trace = TraceSnapshot.model_validate_json(trace_path.read_bytes())
        (run_path,) = (INDEX.parent / "metadata/run").glob("*.run.json")
        full = RunSnapshot.model_validate_json(run_path.read_bytes())
        prefix = []
        for entry in full.entries:
            if entry.kind == "attempt" and entry.event.stage == "closing":
                break
            prefix.append(entry)
        snapshot = RunSnapshot.model_validate(
            full.model_copy(update={"entries": tuple(prefix)})
        )
        source_state = TaskPhaseSourceState(
            intent=plan.intent,
            task=facts.binding,
            public_context_ref=plan.intent.public_context_ref,
            context_receipt_ref=EvidenceRef.model_validate(
                index["member_result"]["closed_source_context_ref"]
            ),
            source_sha256="a" * 64,
        )
        observed: Counter[str] = Counter()
        switches = SimpleNamespace(
            source_changed=False, journal_changed=False, resource_denied=False
        )

        class Sources:
            def read(self, p: Any, op: Any, bounded: Any) -> Any:
                bounded.checkpoint()
                observed["source"] += 1
                return (
                    source_state.model_copy(update={"source_sha256": "b" * 64})
                    if switches.source_changed and observed["source"] % 2 == 0
                    else source_state
                )

            def verify_run(self, *args: Any) -> None:
                raise AssertionError("Unused path")

        class Runs:
            def read(self, op: Any) -> Any:
                observed["journal"] += 1
                return (
                    full
                    if switches.journal_changed and observed["journal"] % 2 == 0
                    else snapshot
                )

        class Rights:
            def verify(self, *args: Any) -> None:
                observed["resource"] += 1
                if switches.resource_denied:
                    raise PermissionError("Current resource rights revoked")

        class Trace:
            def read(self, op: Any) -> Any:
                observed["trace"] += 1
                return trace

        authority = TaskCaptureAuthority(
            capture_ref,
            Sources(),
            cast(Any, Runs()),
            Rights(),
            lambda: cast(Any, Trace()),
            reader,
        )
        inputs = TaskCaptureInputs(
            initialized=initialized,
            initial=initial.selection,
            initial_capture_intent_ref=terminal.initial_capture_intent_ref,
            initial_capture_result_ref=terminal.initial_capture_result_ref,
            initial_checks_ref=terminal.initial_checks_ref,
            environment_selection_ref=terminal.environment_selection_ref,
            prepare_request_ref=terminal.prepare_request_ref,
        )
        # Freeze producers: this test may consume only the existing input graph.
        for cls, name in [
            (RecordedSiteTaskPreparation, "acquire"),
            (RecordedSiteTaskPreparation, "prepare"),
            (RecordedTaskInitialization, "start"),
        ]:
            monkeypatch.setattr(
                cls, name, lambda *a, **kw: pytest.fail("Frozen prefix called")
            )
        yield SimpleNamespace(
            reader=reader,
            plan=plan,
            capture=capture,
            refs=refs,
            control=control,
            scope=scope,
            producer=producer,
            prepared=prepared,
            facts=facts,
            declarations=declarations,
            current=current,
            initial=initial,
            physical_reads=physical_reads,
            terminal_ref=terminal_ref,
            authority=authority,
            inputs=inputs,
            trace=trace,
            observed=observed,
            switches=switches,
            original=original,
        )


def test_original_five_bodies_repeated_with_fresh_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with case(monkeypatch) as c:
        for _ in range(7):
            c.authority.verify(
                c.plan, c.capture, c.inputs, c.trace, c.plan.operation, c.control
            )
        assert c.reader.handoffs == c.reader.reads == 35
        assert not c.physical_reads
        assert c.observed == {"source": 14, "journal": 14, "resource": 7, "trace": 7}
        assert c.current.calls >= 36
    assert c.scope.initial is None and c.scope.preparation_declarations is None
    with pytest.raises(OwnershipConflict):
        c.reader.read(c.plan.reset_plan_ref, c.control)


@pytest.mark.parametrize("fault", ["context", "resource", "source", "journal"])
def test_live_gates_still_refuse_after_valid_body_handoff(
    monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with case(monkeypatch) as c:
        c.authority.verify(
            c.plan, c.capture, c.inputs, c.trace, c.plan.operation, c.control
        )
        if fault == "context":
            c.current.denied = True
        else:
            setattr(
                c.switches,
                {
                    "resource": "resource_denied",
                    "source": "source_changed",
                    "journal": "journal_changed",
                }[fault],
                True,
            )
        with pytest.raises(
            PermissionError if fault in {"context", "resource"} else RevisionConflict
        ):
            c.authority.verify(
                c.plan, c.capture, c.inputs, c.trace, c.plan.operation, c.control
            )
        assert not c.physical_reads
        assert c.observed["source"] >= 2


@pytest.mark.parametrize(
    "fault",
    [
        "producer",
        "schema",
        "digest",
        "missing-preparation",
        "missing-initial",
        "initial-producer",
        "actor",
        "thread",
        "cancel",
        "deadline",
    ],
)
def test_changed_body_scope_or_control_never_falls_back(
    monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with case(monkeypatch) as c:
        ref = c.plan.reset_plan_ref
        expected: type[Exception] = OwnershipConflict
        if fault in {"producer", "schema", "digest"}:
            field = {
                "producer": "producer",
                "schema": "content_schema",
                "digest": "sha256",
            }[fault]
            value = {
                "producer": "foreign",
                "schema": "foreign-schema/1",
                "digest": "b" * 64,
            }[fault]
            ref = ref.model_copy(update={field: value})
        elif fault == "missing-preparation":
            c.scope.preparation_declarations = None
        elif fault == "missing-initial":
            c.scope.initial = None
        elif fault == "initial-producer":
            c.producer.inputs = TaskInitializationInputs(c.plan)
        elif fault == "actor":
            c.producer.state.result = c.producer.state.result.model_copy(
                update={
                    "actor": c.producer.state.result.actor.model_copy(
                        update={
                            "task": c.producer.state.result.actor.task.model_copy(
                                update={"goal": "foreign"}
                            )
                        }
                    )
                }
            )
        elif fault == "thread":
            with ThreadPoolExecutor(max_workers=1) as pool:
                with pytest.raises(OwnershipConflict):
                    pool.submit(c.reader.read, ref, c.control).result()
            assert not c.physical_reads
            return
        elif fault in {"cancel", "deadline"}:

            class Stopped:
                def checkpoint(self) -> float:
                    raise OperationStopped(
                        "CANCELLED" if fault == "cancel" else "DEADLINE_EXCEEDED",
                        "isolated-capture",
                    )

                def wait(self, seconds: float) -> None:
                    self.checkpoint()

            c.control = Stopped()
            expected = OperationStopped
        with pytest.raises(expected):
            c.reader.read(ref, c.control)
        assert not c.physical_reads


def test_other_reference_keeps_original_read_and_wrong_producer_body_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with case(monkeypatch) as c:
        assert c.reader.read(c.terminal_ref, c.control) == c.original.read(
            c.terminal_ref, c.control
        )
        assert sum(c.physical_reads.values()) == 1
        c.scope.initial = c.initial.model_copy(
            update={
                "acquired": c.initial.acquired.model_copy(
                    update={"spec_sha256": "b" * 64}
                )
            }
        )
        with pytest.raises(EvidenceIntegrityError):
            c.reader.read(c.plan.reset_plan_ref, c.control)
        assert sum(c.physical_reads.values()) == 1
