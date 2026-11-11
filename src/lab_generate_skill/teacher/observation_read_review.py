"""Reverse public field checks, independent of the Teacher forward composer."""

from pydantic import JsonValue
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.teacher_actor_material import TeacherActorMaterial
from lab_generate_skill.domain.teacher_json import same_json
from lab_generate_skill.policies.observation_display import observation_read_body


def verify_observation_input_view(
    prompt: ActorPrompt, confirmed: bool, actual: JsonValue
) -> None:
    view = prompt.observation_view
    if view is None:
        raise EvidenceIntegrityError("Original input has no declared observation view")
    source = view.snapshot
    expected = {
        "version": "teacher-actor-observation-view/1",
        "mode": view.mode,
        "delivery": (
            "included_in_model_input" if confirmed else "recorded_input_unconfirmed"
        ),
        "snapshot_sha256": source.observation_ref.sha256,
        "observation_version": source.observation_version,
        "sequence": source.sequence,
        "tab_id": source.tab_id,
        "frame_id": source.frame_id,
        "source_ranges": [span.model_dump(mode="json") for span in view.source_spans],
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
    if not same_json(actual, expected):
        raise EvidenceIntegrityError(
            "Teacher observation view changed actual original ranges/delivery/tools"
        )


def verify_observation_read_event(
    material: TeacherActorMaterial, index: int, actual: JsonValue
) -> None:
    part = material.turns[index]
    fact = part.trace_turn.reading
    if fact is None:
        raise EvidenceIntegrityError("Teacher invented an observation reading")
    requested = fact.request.model_dump(mode="json")
    requested.pop("snapshot")
    requested.pop("request_id")
    requested.pop("schema_version")
    requested["snapshot_sha256"] = fact.request.snapshot.observation_ref.sha256
    sent = []
    for ordinal in range(index + 1, len(material.turns)):
        next_turn = material.turns[ordinal]
        view = next_turn.recorded_input.observation_view
        if (
            fact.result is not None
            and next_turn.completion is not None
            and view is not None
            and view.read_result_ref == fact.result.result_ref
        ):
            sent.append(
                dict(
                    delivery="included_in_model_input",
                    generation_index=ordinal,
                    model_input_sha256=next_turn.completion.model_input_sha256,
                    source_ranges=[
                        span.model_dump(mode="json") for span in view.source_spans
                    ],
                )
            )
    expected = {
        "version": "teacher-actor-observation-read/1",
        "request": requested,
        "status": fact.outcome,
        "return_available": part.reading is not None,
        "returned_result_sha256": (
            None if fact.result is None else fact.result.result_ref.sha256
        ),
        "returned_body": (
            None if part.reading is None else observation_read_body(part.reading)
        ),
        "delivery_records": sent,
        "private_diagnostic_details_withheld": fact.failure_ref is not None,
    }
    if not same_json(actual, expected):
        raise EvidenceIntegrityError(
            "Teacher reading changed original request/result or invented model delivery"
        )
