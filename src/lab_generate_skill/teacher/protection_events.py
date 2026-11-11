"""Independent field/causal checks; never invoke the forward field projector."""

from copy import deepcopy
from pydantic import JsonValue
from lab_generate_skill.domain.teacher_input import (
    PAGE_FIELDS,
    PROTOCOL_FIELDS,
    observation_body,
)
from lab_generate_skill.domain.teacher_json import object_value, array_value, same_json
from lab_generate_skill.domain.teacher_projection import TeacherProjectionPayload
from lab_generate_skill.domain.context_transformation import ContextChange
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from .protection_pages import CompletePageBindings, fragment_sha, layout_change


def _require(value: bool, reason: str) -> None:
    if not value:
        raise EvidenceIntegrityError(reason)


def _protocol(
    source: dict[str, JsonValue],
) -> tuple[dict[str, JsonValue], dict[str, str]]:
    bodies: list[tuple[dict[str, JsonValue], str]] = []
    for i, a in enumerate(array_value(source["attempts"], "All original attempts")):
        attempt = object_value(a, "Original attempt")
        for j, m in enumerate(
            array_value(attempt["trajectory"], "All original messages")
        ):
            body = observation_body(object_value(m, "Original message"))
            if body is not None:
                bodies.append(
                    (body, f"/messages/1/content/attempts/{i}/trajectory/{j}/content")
                )
    result: dict[str, JsonValue] = {}
    anchors: dict[str, str] = {}
    for key in PROTOCOL_FIELDS:
        if not bodies or not all(key in b for b, _ in bodies):
            continue
        first, path = bodies[0]
        if all(same_json(b[key], first[key]) for b, _ in bodies):
            result[key] = first[key]
            anchors[key] = path + "/" + key
    return result, anchors


def complete_events(
    source: dict[str, JsonValue],
    view: TeacherProjectionPayload,
    pages: CompletePageBindings,
) -> tuple[ContextChange, ...]:
    actual = view.evidence
    _require(
        set(actual) == set(source), "Teacher root task/retrieval/extra fields changed"
    )
    for key in source:
        if key not in ("attempts", "initial_observation"):
            _require(
                same_json(source[key], actual[key]),
                "Teacher original root field changed",
            )
    initial = source["initial_observation"]
    assert isinstance(initial, str)
    pages.check(
        actual["initial_observation"],
        initial,
        "/messages/1/content/initial_observation",
    )
    protocol, anchors = _protocol(source)
    _require(
        same_json(protocol, view.observation_protocol),
        "Observation protocol missing/varying/typed values changed",
    )
    old_attempts = array_value(source["attempts"], "Original attempts")
    attempts = array_value(actual["attempts"], "Actual attempts")
    _require(
        len(old_attempts) == len(attempts), "Missing/extra Teacher candidate or round"
    )
    changes: list[ContextChange] = []
    for i, (old, new) in enumerate(zip(old_attempts, attempts, strict=True)):
        original = object_value(old, "Original attempt")
        attempt = object_value(new, "Actual attempt")
        _require(
            set(attempt)
            == (set(original) - {"trajectory"}) | {"candidate_index", "events"},
            "Attempt identities/metadata changed",
        )
        _require(
            type(attempt["candidate_index"]) is int and attempt["candidate_index"] == i,
            "Candidate order/index changed",
        )
        for key, value in original.items():
            if key != "trajectory":
                _require(
                    same_json(value, attempt[key]),
                    "Candidate skill/feedback/status/round/extra changed",
                )
        old_messages = array_value(
            original["trajectory"], "Original complete trajectory"
        )
        events = array_value(attempt["events"], "Actual complete events")
        _require(len(old_messages) == len(events), "Early/missing/extra Teacher event")
        for j, (old_message, new_event) in enumerate(
            zip(old_messages, events, strict=True)
        ):
            message = object_value(old_message, "Original message")
            event = object_value(new_event, "Actual event")
            before = f"/messages/1/content/attempts/{i}/trajectory/{j}"
            after = f"/messages/1/content/evidence/attempts/{i}/events/{j}"
            _require(
                type(event.get("source_message_index")) is int
                and event["source_message_index"] == j,
                "Message order/source index changed",
            )
            required = {"source_message_index", "kind"}
            role = message["role"]
            if role == "user":
                required.add("observation")
                _require(
                    event.get("kind") == "observation",
                    "Original observation became another role",
                )
                body = observation_body(message)
                observed = event.get("observation")
                if body is None:
                    _require(
                        same_json(message["content"], observed),
                        "Opaque/null observation changed",
                    )
                else:
                    observed = object_value(
                        observed, "Complete actual observation object"
                    )
                    expected = deepcopy(body)
                    if "goal" in body and same_json(body["goal"], source["task"]):
                        expected.pop("goal")
                        changes.append(
                            ContextChange(
                                operation="omit_duplicate",
                                source_path=before + "/content/goal",
                                target_path=None,
                                source_sha256=fragment_sha(body["goal"]),
                                target_sha256=None,
                                related_source_paths=("/messages/1/content/task",),
                                reason_code="EXACT_PUBLIC_TASK_REPEATED",
                            )
                        )
                    for key in protocol:
                        expected.pop(key)
                        changes.append(
                            ContextChange(
                                operation="layout",
                                source_path=before + "/content/" + key,
                                target_path="/messages/1/content/observation_protocol/"
                                + key,
                                source_sha256=fragment_sha(body[key]),
                                target_sha256=fragment_sha(
                                    view.observation_protocol[key]
                                ),
                                related_source_paths=(anchors[key],),
                                reason_code="EXACT_GLOBAL_OBSERVATION_PROTOCOL",
                            )
                        )
                    for key in PAGE_FIELDS:
                        text = body.get(key)
                        if isinstance(text, str):
                            _require(
                                key in observed, "Missing complete original page field"
                            )
                            pages.check(observed[key], text, before + "/content/" + key)
                            expected[key] = observed[key]
                    _require(
                        same_json(expected, observed),
                        "Observation controls/values/errors/tabs/provenance/extra changed",
                    )
            elif role == "assistant":
                required |= {"recorded_action", "model_proposal_text"}
                _require(
                    event.get("kind") == "actor_response"
                    and same_json(message["content"], event.get("model_proposal_text")),
                    "Original model proposal changed or omitted",
                )
                action: dict[str, JsonValue] = {}
                if "action_payload" not in message:
                    action["state"] = "missing"
                else:
                    submitted = message["action_payload"]
                    if submitted is None:
                        state = "null"
                    elif isinstance(submitted, str):
                        state = "nonempty" if submitted.strip() else "empty"
                    else:
                        state = "unrecognized_type"
                    action.update(state=state, value=submitted)
                if "action_kind" in message:
                    action["kind"] = message["action_kind"]
                _require(
                    same_json(action, event.get("recorded_action")),
                    "Missing/null/empty/actual recorded action changed",
                )
                for key, index in (
                    ("observation_before", j - 1),
                    ("observation_after", j + 1),
                ):
                    if (
                        0 <= index < len(old_messages)
                        and object_value(
                            old_messages[index], "Adjacent original message"
                        )["role"]
                        == "user"
                    ):
                        required.add(key)
                        _require(
                            type(event.get(key)) is int and event[key] == index,
                            "Causal observation crossed event/candidate",
                        )
            else:
                required |= {"role", "content"}
                _require(
                    event.get("kind") == "other_message"
                    and same_json(event.get("role"), role)
                    and same_json(event.get("content"), message["content"]),
                    "Original non-Actor role/content changed",
                )
            extra = {
                key: value
                for key, value in message.items()
                if key not in {"role", "content"}
                and not (
                    role == "assistant" and key in ("action_kind", "action_payload")
                )
            }
            for key, value in tuple(extra.items()):
                if key == "turn" and type(value) is int and value == j:
                    extra.pop(key)
                    changes.append(
                        layout_change(
                            before + "/turn",
                            after + "/source_message_index",
                            value,
                            j,
                            "EXACT_MESSAGE_POSITION",
                        )
                    )
                elif (
                    role == "user"
                    and key in ("action_kind", "action_payload")
                    and value is None
                ):
                    extra.pop(key)
                    changes.append(
                        ContextChange(
                            operation="layout",
                            source_path=before + "/" + key,
                            target_path=None,
                            source_sha256=fragment_sha(value),
                            target_sha256=None,
                            related_source_paths=(),
                            reason_code="NONASSISTANT_NULL_SERIALIZATION_WRAPPER",
                        )
                    )
            if extra:
                required.add("message_extra")
                _require(
                    same_json(extra, event.get("message_extra")),
                    "Unknown original message fields lost/changed",
                )
            _require(
                set(event) == required,
                "Unexpected/omitted Teacher event field or inferred result",
            )
            changes.append(
                layout_change(
                    before, after, message, event, "COMPLETE_ORIGINAL_EVENT_LAYOUT"
                )
            )
    pages.finish()
    return tuple(changes + pages.changes)
