"""Pure identity for an unexecuted proposal; never a read-progress event."""

import hashlib
import json
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_response import ActorTextCompletion


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate proposal key")
        value[key] = item
    return value


def _finite(value: str) -> object:
    raise ValueError("Nonfinite proposal value")


def rejected_proposal_identity(
    prompt: ActorPrompt, completion: ActorTextCompletion
) -> str | None:
    view = prompt.observation_view
    if view is None or not view.tools:
        return None  # Legacy action-only inputs declare no read policy/threshold.
    decoder = json.JSONDecoder(object_pairs_hook=_unique, parse_constant=_finite)
    proposal: object = completion.text.strip()
    for index, char in enumerate(completion.text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(completion.text[index:])
        except json.JSONDecodeError:
            continue
        except (ValueError, RecursionError):
            break
        if isinstance(value, dict):
            # Thought and JSON key order do not change the proposed operation.
            proposal = {key: item for key, item in value.items() if key != "thought"}
        break
    try:
        raw = json.dumps(
            [
                view.snapshot.model_dump(mode="json"),
                view.policy.model_dump(mode="json"),
                completion.finish_reason,
                proposal,
            ],
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        ).encode()
    except (ValueError, RecursionError):
        # Malformed nonfinite/deep proposals still have a stable bounded identity.
        raw = (
            view.snapshot.model_dump_json()
            + view.policy.model_dump_json()
            + completion.finish_reason
            + completion.text
        ).encode()
    return hashlib.sha256(raw).hexdigest()
