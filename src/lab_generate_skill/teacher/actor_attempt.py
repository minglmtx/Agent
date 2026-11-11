"""Complete original Actor timeline with explicit visibility and outcome stages.

No summary, event selection, hidden references or inference of successful actions.
The full actual Actor user message is the observation page field, so existing
complete body sharing can share it directly without an external lookup.
"""

from pydantic import JsonValue
from lab_generate_skill.domain.observation import ResolvedObservation
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.teacher_actor_material import TeacherActorMaterial
from lab_generate_skill.domain.teacher_source import TeacherAttemptView
from lab_generate_skill.domain.teacher_json import json_text, json_value
from .observation_read import observation_input_view, observation_read_event


def _observed(
    resolved: ResolvedObservation, sent: ActorPrompt | None, confirmed: bool = False
) -> dict[str, JsonValue]:
    record = resolved.record
    active = next((t for t in record.tabs if t.tab_id == record.active_tab_id), None)
    body: dict[str, JsonValue] = {
        "observation_id": record.observation_id,
        "sequence": record.sequence,
        "captured_at": record.captured_at.isoformat(),
        "axtree_txt": resolved.text,
        "state": record.state,
        "error_code": record.error_code,
        "last_action_error": record.last_action_error,
        "open_tabs": [json_value(t.model_dump(mode="json")) for t in record.tabs],
        "active_tab_id": record.active_tab_id,
        "url": None if active is None else active.url,
        "observation_record_source": (
            (
                "original_initial_observation"
                if record.sequence == 0
                else "original_action_return"
            )
            if sent is None
            else "original_generation_input"
        ),
    }
    if sent is not None:
        body["observation"] = sent.messages[1].content
        binding: dict[str, JsonValue] = {
            "version": (
                "teacher-actor-visible-input/1"
                if confirmed
                else "teacher-actor-recorded-input/1"
            ),
            "prompt_version": sent.prompt_version,
            "system_message": sent.messages[0].content,
            "user_message_field": "observation",
            "stage": (
                "original_generation_send" if confirmed else "recorded_generation_input"
            ),
        }
        if not confirmed:
            binding["delivery"] = "unconfirmed"
        body["actor_visible_input" if confirmed else "recorded_actor_input"] = binding
        view = observation_input_view(sent, confirmed)
        if view is not None:
            body["actor_observation_view"] = view
    return body


def actor_attempt(material: TeacherActorMaterial) -> TeacherAttemptView:
    request, trace, evaluation = material.request, material.trace, material.evaluation
    messages: list[JsonValue] = []
    for index, part in enumerate(material.turns):
        t = part.trace_turn
        messages.append(
            {
                "role": "user",
                "content": json_text(
                    _observed(
                        part.before, part.recorded_input, part.completion is not None
                    )
                ),
                "generation_index": index,
            }
        )
        event = t.interaction
        result: dict[str, JsonValue] = {
            "status": "no_recorded_action" if event is None else event.outcome,
            "return_available": part.returned is not None,
            "result": None,
        }
        if part.returned is not None:
            raw = part.returned
            result["result"] = {
                "environment_reward": raw.environment_reward,
                "terminated": raw.terminated,
                "truncated": raw.truncated,
                "protocol_terminal": raw.protocol_terminal,
                "events": [json_value(e.model_dump(mode="json")) for e in raw.events],
            }
        response: dict[str, JsonValue] = {
            "role": "assistant",
            "content": None if part.completion is None else part.completion.text,
            "generation_index": index,
            "generation_status": t.generation.status,
            "finish_reason": (
                None if part.completion is None else part.completion.finish_reason
            ),
            "parsed_decision": None if t.decision is None else t.decision.outcome,
            "operation_result": result,
        }
        if t.decision is not None and t.decision.action is not None:
            response["action_payload"] = t.decision.action.payload
            response["action_kind"] = t.decision.action.name
        if part.parse_failure is not None:
            response["parse_failure"] = {
                "reason_code": part.parse_failure.reason_code,
                "error_type": part.parse_failure.error_type,
                "message": part.parse_failure.message,
            }
        if t.reading is not None:
            response["observation_read"] = observation_read_event(material, index)
        if (
            t.generation.failure_ref is not None
            or (event is not None and event.failure_ref is not None)
            or (t.reading is not None and t.reading.failure_ref is not None)
        ):
            response["private_diagnostic_details"] = (
                "not_projected; original private evidence retained"
            )
        messages.append(response)
        if part.after is not None:
            messages.append(
                {
                    "role": "user",
                    "content": json_text(_observed(part.after, None)),
                    "generation_index": index,
                }
            )
    if not material.turns:
        messages.append(
            {"role": "user", "content": json_text(_observed(material.initial, None))}
        )
    native: dict[str, JsonValue] = {
        "recording_format": (
            "teacher-original-actor-attempt/2"
            if any(
                p.recorded_input.observation_view is not None
                or p.trace_turn.reading is not None
                for p in material.turns
            )
            else "teacher-original-actor-attempt/1"
        ),
        "candidate_slot": material.original.candidate_slot,
        "attempt_id": request.scope.attempt_id,
        "skill": json_value(request.skill.model_payload()),
        "success": (
            True
            if evaluation.status == "success"
            else False if evaluation.status == "failure" else None
        ),
        "steps": trace.interactions,
        "generation_rounds": trace.generations,
        "reward": evaluation.reward,
        "stop_reason": trace.stop_reason,
        "trajectory": messages,
        "evaluator_feedback": {
            "available": True,
            "scope": "original_task_checks; not individual action outcomes",
            "status": evaluation.status,
            "reward": evaluation.reward,
            "checks": [{"name": c.name, "status": c.status} for c in evaluation.checks],
            "private_references_withheld": True,
        },
    }
    if request.candidate_id is not None:
        native["candidate_id"] = request.candidate_id
    if request.revision_round is not None:
        native["revision_round"] = request.revision_round
    return TeacherAttemptView(
        scope=material.original.scope,
        attempt_id=request.scope.attempt_id,
        candidate_slot=material.original.candidate_slot,
        native=native,
    )
