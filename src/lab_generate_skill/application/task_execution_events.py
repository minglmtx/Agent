"""Original task journal/CAS mechanics; no website, role or resource implementation."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.execution import (
    AttemptStage,
    AttemptEvent,
    ExecutionFailure,
    StopReason,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_journal import RunSnapshot, AttemptEntry
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.ports.task_admission import TaskLifecycleAdmission
from lab_generate_skill.domain.task_failure_evidence import TaskModuleFailureEvidence
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls, Clock
from lab_generate_skill.ports.run_journal import RunJournal
from .context_evidence import publish_raw


@dataclass
class TaskExecutionEvents:
    plan: TaskExecutionPlan
    runs: RunJournal
    evidence: EvidenceStore
    controls: OperationControls
    clock: Clock
    snapshot: RunSnapshot
    diagnostics: TaskLifecycleAdmission
    retained: list[EvidenceRef] = field(default_factory=list)
    known: dict[str, EvidenceRef] = field(default_factory=dict)
    last_entry: AttemptEntry | None = None
    _cleanup_limit: tuple[datetime, float] | None = field(default=None, init=False)

    def diagnostic(
        self, name: str, error: BaseException, operation: OperationContext
    ) -> ExecutionFailure:
        confirmed: tuple[EvidenceRef, ...] = ()
        candidates: tuple[EvidenceRef, ...] = ()
        malformed: list[str] = []
        supplied = False
        for attribute in ("references", "candidates"):
            if not hasattr(error, attribute):
                continue
            supplied = True
            value = getattr(error, attribute)
            if not isinstance(value, tuple) or any(
                not isinstance(ref, EvidenceRef) for ref in value
            ):
                malformed.append(attribute + ":" + type(value).__name__)
                continue
            if attribute == "references":
                confirmed = value
            else:
                candidates = value
        if supplied:
            module = TaskModuleFailureEvidence(
                intent=self.plan.intent,
                failure_type=type(error).__name__,
                confirmed_references=confirmed,
                candidate_references=candidates,
                malformed_attributes=tuple(malformed),
            )
            self.put(name + "_module_evidence", module, operation)
        complete = self.diagnostics.failure_context(
            self.plan,
            type(error).__name__,
            tuple(dict.fromkeys((*self.known.values(), *confirmed))),
        )
        reference = self.put(name + "_context", complete, operation)
        return failure_fact(error, (reference,))

    def operation(
        self, name: str, *, cleanup: bool = False, run_level: bool = False
    ) -> OperationContext:
        source = self.plan.read_operation if run_level else self.plan.operation
        identifier = self.plan.operation.operation_id + "." + name
        if cleanup:
            now, elapsed = self.clock.utcnow(), self.clock.monotonic()
            operation = source.cleanup(
                identifier, now=now, seconds=self.plan.cleanup_seconds
            )
            if self._cleanup_limit is None:
                self._cleanup_limit = (
                    operation.deadline,
                    elapsed + self.plan.cleanup_seconds,
                )
            deadline, expires = self._cleanup_limit
            # Closing, restore and sealing share one task allowance. Keep a
            # past cap when exhausted so later bookkeeping cannot renew it;
            # original physical finalizers still run their independent guards.
            return operation.model_copy(
                update={
                    "deadline": min(
                        deadline, now + timedelta(seconds=expires - elapsed)
                    )
                }
            )
        return source.model_copy(update={"operation_id": identifier})

    def put(
        self, name: str, value: Contract, operation: OperationContext
    ) -> EvidenceRef:
        schema = getattr(value, "schema_version", None)
        if not isinstance(schema, str):
            raise ValueError("Versioned complete task facts required")
        ref = publish_raw(
            self.evidence,
            value.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema=schema,
                visibility="private",
                producer="task-execution-v1",
            ),
            self.retained,
            self.controls.bind(operation),
        )
        self.known[name] = ref
        return ref

    def append(
        self,
        stage: AttemptStage,
        operation: OperationContext,
        outputs: tuple[EvidenceRef, ...],
        *,
        cleanup: bool = False,
        primary: ExecutionFailure | None = None,
        failures: tuple[ExecutionFailure, ...] = (),
        stop: StopReason | None = None,
    ) -> RunSnapshot:
        if cleanup:
            read = self.operation(stage + ".journal-read", cleanup=True, run_level=True)
            self.snapshot = RunSnapshot.model_validate(self.runs.read(read))
        records = self.snapshot.project()[1]
        previous = next(
            (a for a in records if a.binding == self.plan.intent.binding), None
        )
        entry = AttemptEntry(
            binding=self.plan.intent.binding,
            event=AttemptEvent(
                stage=stage,
                operation=operation,
                previous_operation_id=(
                    None
                    if previous is None
                    else previous.events[-1].operation.operation_id
                ),
                occurred_at=self.clock.utcnow(),
                component_id="task-lifecycle",
                outputs=outputs,
                stop_reason=stop,
                primary_error=primary,
                cleanup_errors=failures,
            ),
        )
        self.last_entry = entry
        self.snapshot = self.runs.append(entry, self.snapshot.revision, operation)
        return self.snapshot


def failure_fact(
    error: BaseException, references: tuple[EvidenceRef, ...]
) -> ExecutionFailure:
    # The original exception object/chain is retained by TaskExecutionUnconfirmed.
    # Do not serialize arbitrary backend exception text or credentials here.
    return ExecutionFailure(
        component_id="task-lifecycle",
        reason_code="task-execution-unconfirmed",
        message="Original "
        + type(error).__name__
        + "; inspect retained exception and original evidence",
        evidence=references,
    )


def task_stop_reason(error: BaseException | None) -> StopReason | None:
    """Follow explicit module primary chains, never infer a business outcome."""
    if error is None:
        return None
    seen: set[int] = set()
    current = error
    while id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, OperationStopped):
            return "cancelled" if current.reason_code == "CANCELLED" else "timeout"
        primary = getattr(current, "primary", None)
        if not isinstance(primary, BaseException):
            break
        current = primary
    return "error"
