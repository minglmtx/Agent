"""Read actual original browser returns before accepting an issued answer."""

from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    IncompleteAnswerEvidence,
)
from lab_generate_skill.task_families.issued_answer import issued_message
from lab_generate_skill.ports.evaluation_evidence import EvaluationEvidenceReader


def trace_answer(
    trace: InteractionTrace, task: PublicTask, evidence: EvaluationEvidenceReader
) -> str | None:
    initial = evidence.read(
        trace.initial_observation_ref, "observation/1", Observation, public=True
    )
    if (initial.task, initial.context_id, initial.attempt_id, initial.sequence) != (
        trace.scope.task,
        trace.scope.context_id,
        trace.scope.attempt_id,
        0,
    ):
        raise EvidenceIntegrityError(
            "Answer trace changed original initial observation"
        )
    sequence = 0
    answer: str | None = None
    for turn in trace.turns:
        event = turn.interaction
        if event is None:
            continue
        if event.outcome != "returned" or event.result is None:
            raise IncompleteAnswerEvidence("Original browser action return incomplete")
        result = event.result
        returned = evidence.read(
            result.return_ref, "browser-step-return/1", BrowserReadout
        )
        observed = evidence.read(
            result.observation_ref, "observation/1", Observation, public=True
        )
        sequence += 1
        if (
            returned.scope != trace.scope
            or returned.action != event.action
            or returned.operation != event.operation
            or returned.observation != observed
            or observed.sequence != sequence
            or result.terminal
            != (returned.terminated or returned.truncated or returned.protocol_terminal)
        ):
            raise EvidenceIntegrityError(
                "Answer trace differs from original browser step"
            )
        message = issued_message(event.action, returned, task)
        if message is not None:
            answer = message
    return answer
