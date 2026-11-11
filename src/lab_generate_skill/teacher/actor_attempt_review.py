"""Independent check of every emitted native field against original typed leaves.

Never imports or invokes the forward Actor timeline composer. No I/O or model.
"""

from pydantic import JsonValue
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.observation import ResolvedObservation
from lab_generate_skill.domain.teacher_actor_material import TeacherActorMaterial
from lab_generate_skill.domain.teacher_source import TeacherAttemptView
from lab_generate_skill.domain.teacher_json import (
    object_value,
    array_value,
    read_json,
    same_json,
    json_value,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from .observation_read_review import (
    verify_observation_input_view,
    verify_observation_read_event,
)


def _check(condition: bool) -> None:
    if not condition:
        raise EvidenceIntegrityError(
            "Native Teacher attempt changed/omitted original permitted fields or invented outcomes"
        )


def _observation(
    message: JsonValue,
    resolved: ResolvedObservation,
    sent: ActorPrompt | None,
    index: int | None,
    confirmed: bool = False,
) -> None:
    m = object_value(message, "Original observation message required")
    _check(
        set(m)
        == (
            {"role", "content"}
            if index is None
            else {"role", "content", "generation_index"}
        )
    )
    _check(
        m["role"] == "user"
        and (index is None or same_json(m["generation_index"], index))
    )
    content = m["content"]
    _check(type(content) is str)
    assert isinstance(content, str)
    body = object_value(
        read_json(content), "Original complete observation object required"
    )
    record = resolved.record
    active = next((t for t in record.tabs if t.tab_id == record.active_tab_id), None)
    expected: dict[str, JsonValue] = {
        "observation_id": record.observation_id,
        "sequence": record.sequence,
        "captured_at": record.captured_at.isoformat(),
        "axtree_txt": resolved.text,
        "state": record.state,
        "error_code": record.error_code,
        "last_action_error": record.last_action_error,
        "open_tabs": [t.model_dump(mode="json") for t in record.tabs],
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
    binding_key = "actor_visible_input" if confirmed else "recorded_actor_input"
    view_keys = (
        {"actor_observation_view"}
        if sent is not None and sent.observation_view is not None
        else set()
    )
    _check(
        set(body)
        == set(expected)
        | ({"observation", binding_key} if sent is not None else set())
        | view_keys
    )
    for key, value in expected.items():
        _check(same_json(body[key], value))
    if sent is not None:
        if sent.observation_view is not None:
            verify_observation_input_view(
                sent, confirmed, body["actor_observation_view"]
            )
        _check(same_json(body["observation"], sent.messages[1].content))
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
        _check(same_json(body[binding_key], binding))


def verify_actor_attempt(
    material: TeacherActorMaterial, actual: TeacherAttemptView
) -> None:
    actual = TeacherAttemptView.model_validate(actual)
    request, trace, evaluation = material.request, material.trace, material.evaluation
    _check(
        (actual.scope, actual.attempt_id, actual.candidate_slot)
        == (
            material.original.scope,
            request.scope.attempt_id,
            material.original.candidate_slot,
        )
    )
    body = actual.native
    keys = {
        "recording_format",
        "candidate_slot",
        "attempt_id",
        "skill",
        "success",
        "steps",
        "generation_rounds",
        "reward",
        "stop_reason",
        "trajectory",
        "evaluator_feedback",
    }
    if request.candidate_id is not None:
        keys.add("candidate_id")
    if request.revision_round is not None:
        keys.add("revision_round")
    _check(set(body) == keys)
    values: dict[str, JsonValue] = {
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
            None if evaluation.status == "unknown" else evaluation.status == "success"
        ),
        "steps": trace.interactions,
        "generation_rounds": trace.generations,
        "reward": evaluation.reward,
        "stop_reason": trace.stop_reason,
    }
    if request.candidate_id is not None:
        values["candidate_id"] = request.candidate_id
    if request.revision_round is not None:
        values["revision_round"] = request.revision_round
    for key, value in values.items():
        _check(same_json(body[key], value))
    _check(
        same_json(
            body["evaluator_feedback"],
            {
                "available": True,
                "scope": "original_task_checks; not individual action outcomes",
                "status": evaluation.status,
                "reward": evaluation.reward,
                "checks": [
                    {"name": c.name, "status": c.status} for c in evaluation.checks
                ],
                "private_references_withheld": True,
            },
        )
    )
    messages = array_value(body["trajectory"], "Complete native trajectory required")
    _check(
        len(messages)
        == (
            1
            if not material.turns
            else sum(2 + int(p.after is not None) for p in material.turns)
        )
    )
    position = 0
    if not material.turns:
        _observation(messages[0], material.initial, None, None)
    for index, part in enumerate(material.turns):
        _observation(
            messages[position],
            part.before,
            part.recorded_input,
            index,
            part.completion is not None,
        )
        position += 1
        response = object_value(messages[position], "Original native response required")
        position += 1
        t = part.trace_turn
        event = t.interaction
        required = {
            "role",
            "content",
            "generation_index",
            "generation_status",
            "finish_reason",
            "parsed_decision",
            "operation_result",
        }
        if t.decision is not None and t.decision.action is not None:
            required |= {"action_kind", "action_payload"}
            _check(
                same_json(response.get("action_kind"), t.decision.action.name)
                and same_json(response.get("action_payload"), t.decision.action.payload)
            )
        if part.parse_failure is not None:
            required.add("parse_failure")
            _check(
                same_json(
                    response.get("parse_failure"),
                    {
                        "reason_code": part.parse_failure.reason_code,
                        "error_type": part.parse_failure.error_type,
                        "message": part.parse_failure.message,
                    },
                )
            )
        if t.reading is not None:
            required.add("observation_read")
            verify_observation_read_event(
                material, index, response.get("observation_read")
            )
        if (
            t.generation.failure_ref is not None
            or (event is not None and event.failure_ref is not None)
            or (t.reading is not None and t.reading.failure_ref is not None)
        ):
            required.add("private_diagnostic_details")
            _check(
                response.get("private_diagnostic_details")
                == "not_projected; original private evidence retained"
            )
        _check(set(response) == required)
        for key, value in {
            "role": "assistant",
            "content": None if part.completion is None else part.completion.text,
            "generation_index": index,
            "generation_status": t.generation.status,
            "finish_reason": (
                None if part.completion is None else part.completion.finish_reason
            ),
            "parsed_decision": None if t.decision is None else t.decision.outcome,
        }.items():
            _check(same_json(response[key], value))
        result = object_value(
            response["operation_result"], "Original action status required"
        )
        _check(set(result) == {"status", "return_available", "result"})
        _check(
            result["status"]
            == ("no_recorded_action" if event is None else event.outcome)
        )
        _check(same_json(result["return_available"], part.returned is not None))
        raw = part.returned
        if raw is None:
            _check(result["result"] is None)
        else:
            _check(
                same_json(
                    result["result"],
                    {
                        "environment_reward": raw.environment_reward,
                        "terminated": raw.terminated,
                        "truncated": raw.truncated,
                        "protocol_terminal": raw.protocol_terminal,
                        "events": [e.model_dump(mode="json") for e in raw.events],
                    },
                )
            )
        if part.after is not None:
            _observation(messages[position], part.after, None, index)
            position += 1
