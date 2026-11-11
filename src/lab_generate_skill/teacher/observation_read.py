"""Public reading and exact delivery facts; no private scope/count references."""

from pydantic import JsonValue
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.teacher_actor_material import TeacherActorMaterial
from lab_generate_skill.domain.teacher_json import json_value
from lab_generate_skill.policies.observation_display import observation_read_body


def observation_input_view(
    prompt: ActorPrompt, confirmed: bool
) -> dict[str, JsonValue] | None:
    view = prompt.observation_view
    if view is None:
        return None
    snapshot = view.snapshot
    return {
        "version": "teacher-actor-observation-view/1",
        "mode": view.mode,
        "delivery": (
            "included_in_model_input" if confirmed else "recorded_input_unconfirmed"
        ),
        "snapshot_sha256": snapshot.observation_ref.sha256,
        "observation_version": snapshot.observation_version,
        "sequence": snapshot.sequence,
        "tab_id": snapshot.tab_id,
        "frame_id": snapshot.frame_id,
        "source_ranges": [
            json_value(span.model_dump(mode="json")) for span in view.source_spans
        ],
        "body_start": view.body_start,
        "body_end": view.body_end,
        "body_sha256": view.body_sha256,
        "active_read_result_sha256": (
            None if view.read_result_ref is None else view.read_result_ref.sha256
        ),
        "registered_read_tools": list(view.tools),
        "reads_used": view.reads_used,
        "reads_remaining": max(0, view.policy.reads_per_observation - view.reads_used),
        "no_progress": view.no_progress,
    }


def observation_read_event(
    material: TeacherActorMaterial, index: int
) -> dict[str, JsonValue]:
    part = material.turns[index]
    fact = part.trace_turn.reading
    assert fact is not None
    request = fact.request
    choice = request.model_dump(
        mode="json", exclude={"schema_version", "request_id", "snapshot"}
    )
    choice["snapshot_sha256"] = request.snapshot.observation_ref.sha256
    deliveries: list[JsonValue] = []
    if fact.result is not None:
        for later_index, later in enumerate(
            material.turns[index + 1 :], start=index + 1
        ):
            view = later.recorded_input.observation_view
            if (
                later.completion is not None
                and view is not None
                and view.read_result_ref == fact.result.result_ref
            ):
                deliveries.append(
                    {
                        "delivery": "included_in_model_input",
                        "generation_index": later_index,
                        "model_input_sha256": later.completion.model_input_sha256,
                        "source_ranges": [
                            json_value(span.model_dump(mode="json"))
                            for span in view.source_spans
                        ],
                    }
                )
    return {
        "version": "teacher-actor-observation-read/1",
        "request": json_value(choice),
        "status": fact.outcome,
        "return_available": part.reading is not None,
        "returned_result_sha256": (
            None if fact.result is None else fact.result.result_ref.sha256
        ),
        "returned_body": (
            None if part.reading is None else observation_read_body(part.reading)
        ),
        "delivery_records": deliveries,
        "private_diagnostic_details_withheld": fact.failure_ref is not None,
    }
