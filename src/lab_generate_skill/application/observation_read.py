"""Original write-ahead readonly execution, with independent return recording.

No model inference, browser step, site recapture or automatic recovery/retry.
Known body/count/ref survive result or journal failure in the typed exception.
"""

from lab_generate_skill.domain.observation_read_dispatch import ObservationReadDispatch
from lab_generate_skill.domain.observation_read_fact import (
    ObservationReadFact,
    ObservationReadFailure,
)
from lab_generate_skill.domain.observation_read_return import (
    ReturnedObservationRead,
    ObservationReadUnconfirmed,
)
from lab_generate_skill.domain.observation_read_progress import ObservationReadRecord
from lab_generate_skill.domain.trace import observation_progress_from_turns
from lab_generate_skill.domain.trace_events import ReadObserved
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.observation_reads import ObservationReads
from lab_generate_skill.ports.trace_journal import TraceJournal
from lab_generate_skill.ports.lifecycle import OperationControls, OperationControl
from lab_generate_skill.ports.evidence import EvidenceStore


class ObservationReadDispatchFailure(RuntimeError):
    def __init__(
        self,
        request: ObservationReadDispatch,
        phase: str,
        primary: BaseException,
        acknowledged: TraceSnapshot | None,
        returned: object,
        observed: ReadObserved | None,
        after: TraceSnapshot | None = None,
    ) -> None:
        self.request, self.phase, self.primary = request, phase, primary
        self.acknowledged, self.returned, self.observed, self.after = (
            acknowledged,
            returned,
            observed,
            after,
        )
        super().__init__(
            f"Original readonly dispatch stopped in {phase}; preserve known result without redispatch"
        )


def _failure_reference(
    value: ObservationReadFailure, evidence: EvidenceStore, control: OperationControl
) -> EvidenceRef:
    raw = value.model_dump_json().encode()
    metadata = EvidenceMetadata(
        media_type="application/json",
        content_schema=value.schema_version,
        visibility="private",
        producer="actor-observation-read-v1",
    )
    candidate = evidence_reference(raw, metadata)
    reference: EvidenceRef | None = None
    try:
        reference = evidence.put(raw, metadata, control)
        if reference.model_dump(exclude={"uri"}) != candidate.model_dump(
            exclude={"uri"}
        ):
            raise EvidenceIntegrityError(
                "Reading failure publication changed original facts"
            )
        control.checkpoint()
        return reference
    except BaseException as error:
        setattr(error, "observation_read_failure_candidate", candidate)
        setattr(error, "observation_read_failure_reference", reference)
        raise


def execute_observation_read(
    request: ObservationReadDispatch,
    journal: TraceJournal,
    readings: ObservationReads,
    evidence: EvidenceStore,
    controls: OperationControls,
) -> TraceSnapshot:
    request = ObservationReadDispatch.model_validate(request)
    intent = request.intent
    choice = intent.decision.read_request
    policy = intent.decision.read_policy
    assert choice is not None and policy is not None
    phase = "commit_intent"
    acknowledged: TraceSnapshot | None = None
    returned: object = None
    observed: ReadObserved | None = None
    after: TraceSnapshot | None = None
    try:
        control = controls.bind(intent.execution_operation)
        control.checkpoint()
        acknowledged = TraceSnapshot.model_validate(
            journal.append(intent, request.expected_revision, intent.operation)
        )
        view = acknowledged.project()
        if (
            acknowledged.revision != request.expected_revision + 1
            or acknowledged.events[-1] != intent
            or view.reading != intent
            or view.generation is None
        ):
            raise OwnershipConflict(
                "Journal did not acknowledge exact first reading intent"
            )
        progress = observation_progress_from_turns(
            tuple(view.turns),
            choice.snapshot,
            policy,
            initial_displayed_spans=intent.decision.displayed_source_spans,
            initial_progress_fingerprint=intent.decision.active_progress_fingerprint,
        )
        phase = "read"
        result: ObservationReadRecord | None = None
        failure_ref: EvidenceRef | None = None
        outcome = "returned"
        read_error: BaseException | None = None
        try:
            returned = readings.read(
                choice,
                intent.execution_operation,
                progress=progress,
                control=control,
                retention_control=controls.bind(request.result_operation),
            )
            actual = ReturnedObservationRead.model_validate(returned)
            if actual.payload.request != choice:
                raise OwnershipConflict(
                    "Original reading result changed its request/options"
                )
            result = actual.record
            progress.returned(result)
        except BaseException as error:
            read_error = error
            outcome = "failed"
            candidate_ref = None
            if isinstance(error, ObservationReadUnconfirmed):
                candidate_ref = error.result_ref
                if candidate_ref is not None:
                    try:
                        actual = ReturnedObservationRead(
                            result_ref=candidate_ref,
                            payload=error.payload,
                            body=error.body,
                            count=error.count,
                        )
                        if actual.payload.request == choice:
                            result = actual.record
                            outcome = "returned_unconfirmed"
                    except (ValueError, EvidenceIntegrityError, OwnershipConflict):
                        pass  # Preserve the candidate and original error, no fabricated validated return.
            diagnostic = ObservationReadFailure(
                generation_id=intent.decision.generation_id,
                request=choice,
                error_type=type(error).__name__,
                message=str(error)[:4096],
                returned_result_ref=candidate_ref,
            )
            phase = "save_failure"
            failure_ref = _failure_reference(
                diagnostic, evidence, controls.bind(request.result_operation)
            )
        phase = "commit_result"
        reading = ObservationReadFact.model_validate(
            dict(
                scope=acknowledged.plan.scope,
                operation=intent.execution_operation,
                generation_id=intent.decision.generation_id,
                request=choice,
                outcome=outcome,
                result=result,
                failure_ref=failure_ref,
            )
        )
        observed = ReadObserved(operation=request.result_operation, reading=reading)
        after = TraceSnapshot.model_validate(
            journal.append(observed, acknowledged.revision, request.result_operation)
        )
        if (
            after.plan != acknowledged.plan
            or after.creation_operation != acknowledged.creation_operation
            or after.events != (*acknowledged.events, observed)
        ):
            raise OwnershipConflict("Journal did not confirm original readonly return")
        if read_error is not None:
            raise ObservationReadDispatchFailure(
                request,
                "read_return_recorded",
                read_error,
                acknowledged,
                returned,
                observed,
                after,
            )
        return after
    except ObservationReadDispatchFailure:
        raise
    except BaseException as error:
        raise ObservationReadDispatchFailure(
            request, phase, error, acknowledged, returned, observed, after
        ) from error
