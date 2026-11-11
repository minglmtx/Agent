"""Migrate native complete-field projection and exact one-hop body sharing.

No I/O, model, tokenizer, page selection, learned summary or arithmetic deltas.
Every attempt/event retains its own identity/order, even when page bytes match.
"""

from copy import deepcopy
from pydantic import JsonValue
from lab_generate_skill.domain.teacher_input import (
    PAGE_FIELDS,
    PROTOCOL_FIELDS,
    observation_body,
)
from lab_generate_skill.domain.teacher_json import object_value, array_value, same_json
from lab_generate_skill.domain.teacher_projection import (
    TeacherProjectionPayload,
    TeacherSharedPage,
)


def project_fields(evidence: dict[str, JsonValue]) -> TeacherProjectionPayload:
    output = deepcopy(evidence)
    attempts = array_value(output.pop("attempts"), "All complete attempts required")
    observations: list[dict[str, JsonValue]] = []
    for value in attempts:
        attempt = object_value(value, "Original attempt required")
        for item in array_value(attempt["trajectory"], "Complete trajectory required"):
            body = observation_body(object_value(item, "Original message required"))
            if body is not None:
                observations.append(body)
    protocol: dict[str, JsonValue] = {}
    for key in PROTOCOL_FIELDS:
        values = [body[key] for body in observations if key in body]
        if (
            values
            and len(values) == len(observations)
            and all(same_json(values[0], value) for value in values)
        ):
            protocol[key] = deepcopy(values[0])
    pages: list[TeacherSharedPage] = []
    ids: dict[str, str] = {}

    def page(text: str) -> dict[str, JsonValue]:
        if text not in ids:
            ids[text] = "p" + str(len(pages))
            pages.append(TeacherSharedPage(page_id=ids[text], text=text))
        return {"page_ref": ids[text]}

    initial = evidence["initial_observation"]
    assert isinstance(initial, str)
    output["initial_observation"] = page(initial)
    projected: list[JsonValue] = []
    for i, value in enumerate(attempts):
        attempt = object_value(value, "Original attempt required")
        messages = array_value(
            attempt.pop("trajectory"), "Complete trajectory required"
        )
        events: list[JsonValue] = []
        for j, item in enumerate(messages):
            message = object_value(item, "Original message required")
            role = message["role"]
            body = observation_body(message)
            event: dict[str, JsonValue] = {"source_message_index": j}
            if role == "user":
                event["kind"] = "observation"
                if body is None:
                    event["observation"] = deepcopy(message["content"])
                else:
                    body = deepcopy(body)
                    if "goal" in body and same_json(body["goal"], evidence["task"]):
                        body.pop("goal")
                    for key in protocol:
                        body.pop(key)
                    for key in PAGE_FIELDS:
                        text = body.get(key)
                        if isinstance(text, str):
                            body[key] = page(text)
                    event["observation"] = body
            elif role == "assistant":
                event["kind"] = "actor_response"
                payload = message.get("action_payload")
                state = (
                    "missing"
                    if "action_payload" not in message
                    else (
                        "null"
                        if payload is None
                        else (
                            "empty"
                            if isinstance(payload, str) and not payload.strip()
                            else (
                                "nonempty"
                                if isinstance(payload, str)
                                else "unrecognized_type"
                            )
                        )
                    )
                )
                action: dict[str, JsonValue] = {"state": state}
                if "action_payload" in message:
                    action["value"] = deepcopy(payload)
                if "action_kind" in message:
                    action["kind"] = deepcopy(message["action_kind"])
                event["recorded_action"] = action
                event["model_proposal_text"] = deepcopy(message["content"])
                if (
                    j
                    and object_value(messages[j - 1], "Original adjacent message")[
                        "role"
                    ]
                    == "user"
                ):
                    event["observation_before"] = j - 1
                if (
                    j + 1 < len(messages)
                    and object_value(messages[j + 1], "Original adjacent message")[
                        "role"
                    ]
                    == "user"
                ):
                    event["observation_after"] = j + 1
            else:
                event.update(
                    kind="other_message",
                    role=deepcopy(role),
                    content=deepcopy(message["content"]),
                )
            reserved = {"role", "content"} | (
                {"action_kind", "action_payload"} if role == "assistant" else set()
            )
            extras: dict[str, JsonValue] = {}
            for key, value in message.items():
                if key in reserved:
                    continue
                if key == "turn" and type(value) is int and value == j:
                    continue
                if (
                    role == "user"
                    and key in ("action_kind", "action_payload")
                    and value is None
                ):
                    continue
                extras[key] = deepcopy(value)
            if extras:
                event["message_extra"] = extras
            events.append(event)
        attempt["candidate_index"] = i
        attempt["events"] = events
        projected.append(attempt)
    output["attempts"] = projected
    return TeacherProjectionPayload(
        observation_protocol=protocol, pages=tuple(pages), evidence=output
    )
