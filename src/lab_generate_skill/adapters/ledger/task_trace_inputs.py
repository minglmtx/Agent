"""Verified event references and resolved observations of one original task.

Full bytes are verified at their real event read. Sealing consumes those exact
facts and immutable observation bodies, never re-walks old payloads. No event
commit, permission, persistent state, cross-job reuse or dispatch is inferred.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evidence_dependencies import evidence_references
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.observation import Observation, ResolvedObservation
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.trace_events import TraceProgressEvent, TraceSealed
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.trace_plan import TracePlan
from lab_generate_skill.domain.trace_progress import check_trace_operation
from lab_generate_skill.domain.verified_evidence_body import VerifiedEvidenceBody
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.trace_body_inputs import TraceBodyScope


class TaskTraceEventInputs:
    def __init__(self, plan: TracePlan, scope: TraceBodyScope) -> None:
        self.plan = TracePlan.model_validate(plan)
        if scope.task_identity != plan.scope.task:
            raise OwnershipConflict("Trace inputs changed original task")
        self.scope = scope
        self._verified: set[EvidenceRef] = set()
        self._expected: set[EvidenceRef] = set()
        self._observations: dict[EvidenceRef, ResolvedObservation] = {}
        self._expected_observations: set[EvidenceRef] = set()
        self._closed = False
        self._event_active = False
        self._active_seal: tuple[TraceSnapshot, TraceSealed] | None = None
        self._validated_seal: InteractionTrace | None = None
        self._sealed: InteractionTrace | None = None
        self.statistics = {
            "event_body_reads": 0,
            "event_verified_reuses": 0,
            "seal_body_reads": 0,
            "seal_verified_reuses": 0,
            "observation_reuses": 0,
            "verified_event_groups": 0,
        }

    @property
    def retained_refs(self) -> frozenset[EvidenceRef]:
        return frozenset(self._verified)

    def _check(self, op: OperationContext, control: OperationControl) -> None:
        self.scope.check(op, control)
        check_trace_operation(self.plan, op)
        if self._closed:
            raise OwnershipConflict("Original trace input lifetime closed")

    @contextmanager
    def event_inputs(
        self,
        before: TraceSnapshot,
        event: TraceProgressEvent,
        op: OperationContext,
        original: EvidenceReader,
        control: OperationControl,
    ) -> Iterator[EvidenceReader]:
        self._check(op, control)
        if before.plan != self.plan or self._event_active:
            raise OwnershipConflict(
                "Original trace plan required; verifier is not reentrant"
            )
        check_trace_operation(self.plan, event.operation)
        read = _TraceEventReader(
            self, set(evidence_references(event)), original, op, "event"
        )
        self._event_active = True
        if isinstance(event, TraceSealed):
            self._active_seal = (before, event)
        try:
            yield read
            self._check(op, control)
            if isinstance(event, TraceSealed):
                if self._validated_seal is None:
                    raise OwnershipConflict("Original sealed trace validation missing")
                self._sealed = self._validated_seal
            self._verified.update(read.verified)
            self._expected.update(read.verified)
            self._observations.update(read.observed)
            self._expected_observations.update(read.observed)
            self.statistics["verified_event_groups"] += 1
        finally:
            read.close()
            self._event_active = False
            self._active_seal = None
            self._validated_seal = None

    @contextmanager
    def sealing_inputs(
        self,
        trace: InteractionTrace,
        op: OperationContext,
        original: EvidenceReader,
        control: OperationControl,
    ) -> Iterator[EvidenceReader]:
        self._check(op, control)
        if self._active_seal is not None:
            before, event = self._active_seal
            expected = before.project()
            expected.advance(self.plan, event)
            if expected.sealed != trace:
                raise OwnershipConflict("Seal changed original checked event history")
        elif self._sealed != trace:
            raise OwnershipConflict("Original same-call sealed trace required")
        allowed = set(evidence_references(trace))
        if (allowed & self._expected) - self._verified:
            raise OwnershipConflict("Verified event input missing; no history rebuild")
        read = _TraceEventReader(self, allowed, original, op, "seal")
        try:
            yield read
            self._check(op, control)
            if self._active_seal is not None:
                self._validated_seal = trace
        finally:
            read.close()

    def clear(self) -> None:
        self._closed = True
        self._verified.clear()
        self._expected.clear()
        self._observations.clear()
        self._expected_observations.clear()
        self._sealed = self._validated_seal = None
        self._active_seal = None


class _TraceEventReader:
    def __init__(
        self,
        owner: TaskTraceEventInputs,
        allowed: set[EvidenceRef],
        original: EvidenceReader,
        op: OperationContext,
        phase: str,
    ) -> None:
        self.owner, self.allowed, self.original, self.op, self.phase = (
            owner,
            allowed,
            original,
            op,
            phase,
        )
        self.verified: set[EvidenceRef] = set()
        self.observed: dict[EvidenceRef, ResolvedObservation] = {}
        self._observation_bytes: dict[EvidenceRef, VerifiedEvidenceBody] = {}
        self.active = True

    def _check(self, control: OperationControl) -> None:
        self.owner._check(self.op, control)
        if not self.active:
            raise OwnershipConflict("Trace reader left original verifier")

    def verify_trace_reference(
        self, reference: EvidenceRef, control: OperationControl
    ) -> bool:
        self._check(control)
        if reference not in self.allowed:
            return False
        if reference in self.owner._expected and reference not in self.owner._verified:
            raise OwnershipConflict("Verified event input missing; no history rebuild")
        known = reference in self.verified or reference in self.owner._verified
        if (
            not known
            and isinstance(self.original, _TraceEventReader)
            and self.original.owner is self.owner
        ):
            known = self.original.verify_trace_reference(reference, control)
            if known:
                self.verified.add(reference)
        if known:
            self.owner.statistics[self.phase + "_verified_reuses"] += 1
        return known

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        self._check(control)
        reference = EvidenceRef.model_validate(reference)
        if reference not in self.allowed:
            return self.original.read(reference, control)
        old = self._observation_bytes.get(reference)
        if old is not None:
            return old.raw
        body = VerifiedEvidenceBody(reference, self.original.read(reference, control))
        self.verified.add(reference)
        self.owner.statistics[self.phase + "_body_reads"] += 1
        if reference.content_schema == "observation/1":
            observed = Observation.model_validate_json(body.raw)
            if (observed.task, observed.context_id, observed.attempt_id) != (
                self.owner.plan.scope.task,
                self.owner.plan.scope.context_id,
                self.owner.plan.scope.attempt_id,
            ):
                raise OwnershipConflict("Trace observation changed original scope")
            self._observation_bytes[reference] = body
            self.allowed.update(evidence_references(observed))
        self._check(control)
        return body.raw

    def observation_inputs(
        self,
        reference: EvidenceRef,
        control: OperationControl,
    ) -> ResolvedObservation | None:
        self._check(control)
        if reference not in self.allowed:
            return None
        if (
            reference in self.owner._expected_observations
            and reference not in self.owner._observations
        ):
            raise OwnershipConflict("Verified observation missing; no history rebuild")
        value = self.observed.get(reference) or self.owner._observations.get(reference)
        if value is not None:
            self.owner.statistics["observation_reuses"] += 1
        return value

    def observed_inputs(
        self,
        reference: EvidenceRef,
        observation: ResolvedObservation,
        control: OperationControl,
    ) -> None:
        self._check(control)
        if reference not in self.allowed:
            return
        old = self.observation_inputs(reference, control)
        if old is not None:
            if old != observation:
                raise EvidenceIntegrityError("Resolved trace observation changed")
            return
        body = self._observation_bytes.get(reference)
        if (
            body is None
            or Observation.model_validate_json(body.raw) != observation.record
        ):
            raise EvidenceIntegrityError(
                "Original read/validated observation body required"
            )
        self.observed[reference] = observation

    def close(self) -> None:
        self.active = False
        self.verified.clear()
        self.observed.clear()
        self._observation_bytes.clear()
