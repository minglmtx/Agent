"""Parse only a read tool declared in this original actual input; no dispatch."""

import json
from pydantic import TypeAdapter
from lab_generate_skill.domain.actor_prompt import ActorPrompt, MAX_ACTOR_RESPONSE_BYTES
from lab_generate_skill.domain.observation_read import (
    ObservationReadRequest,
    ListObservationRegions,
    ReadObservationRegions,
    SearchObservationRegions,
)
from lab_generate_skill.domain.observation_read_choice import (
    ActorObservationReadChoice,
    ListObservationChoice,
    ReadObservationChoice,
)
from .response import _pairs, _constant

_CHOICE: TypeAdapter[ActorObservationReadChoice] = TypeAdapter(
    ActorObservationReadChoice
)


def parse_observation_read(
    text: str, finish_reason: str, prompt: ActorPrompt, *, request_id: str
) -> ObservationReadRequest | None:
    prompt = ActorPrompt.model_validate(prompt)
    from .schema_response import NEW_PROMPTS, current_tool_schemas, schema_read

    if prompt.prompt_version in NEW_PROMPTS:
        from lab_generate_skill.policies.actor_proposal_syntax import proposal_object

        return schema_read(
            proposal_object(text, finish_reason),
            prompt,
            current_tool_schemas(prompt, ()),
            request_id,
        )
    if type(text) is not str or type(finish_reason) is not str:
        raise TypeError("Actor response and finish reason must be strings")
    if (
        finish_reason != "stop"
        or not 0 < len(text.encode()) <= MAX_ACTOR_RESPONSE_BYTES
    ):
        raise ValueError("Actor response unfinished, empty or outside byte budget")
    decoder = json.JSONDecoder(object_pairs_hook=_pairs, parse_constant=_constant)
    value = None
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        break
    if not isinstance(value, dict) or "read" not in value:
        return None
    if set(value) - {"thought", "read"} or not isinstance(
        value.get("thought", ""), str
    ):
        raise ValueError("Actor must propose exactly one read or one business action")
    view = prompt.observation_view
    if view is None or prompt.prompt_version not in (
        "browsergym-adaptive-full-ax-v1",
        "browsergym-adaptive-local-ax-v1",
        "browsergym-adaptive-full-ax-v2",
        "browsergym-adaptive-local-ax-v2",
    ):
        raise ValueError(
            "Observation read tool was not registered in this original Actor input"
        )
    # The effective frozen policy is stricter than the transport's absolute
    # schema ceiling. Explain that actual limit before schema validation.
    proposal = value["read"]
    if isinstance(proposal, dict) and proposal.get("tool") == "read_region":
        ranges = proposal.get("ranges")
        if isinstance(ranges, list) and len(ranges) > view.policy.max_ranges:
            raise ValueError(
                "Observation read was not executed. "
                f"maximum_ranges={view.policy.max_ranges}; submitted_ranges={len(ranges)}. "
                "Reduce the request to the allowed range count. Region IDs must come from "
                "the current snapshot's directory; use list_regions first for unknown IDs."
            )
    choice = _CHOICE.validate_json(
        json.dumps(value["read"], ensure_ascii=False, allow_nan=False)
    )
    if choice.tool not in view.tools:
        raise ValueError("Selected read tool is not an actual registered capability")
    if choice.snapshot_sha256 != view.snapshot.observation_ref.sha256:
        raise ValueError("Read choice changed current public snapshot")
    if choice.output_tokens > view.policy.body_max_tokens:
        raise ValueError("Read output exceeds original shared local-body limit")
    if isinstance(choice, ListObservationChoice):
        return ListObservationRegions(
            request_id=request_id,
            snapshot=view.snapshot,
            output_tokens=choice.output_tokens,
            continuation=choice.continuation,
            parent_region_id=choice.parent_region_id,
        )
    if isinstance(choice, ReadObservationChoice):
        return ReadObservationRegions(
            request_id=request_id,
            snapshot=view.snapshot,
            output_tokens=choice.output_tokens,
            continuation=choice.continuation,
            ranges=choice.ranges,
        )
    return SearchObservationRegions(
        request_id=request_id,
        snapshot=view.snapshot,
        output_tokens=choice.output_tokens,
        continuation=choice.continuation,
        query=choice.query,
        mode=choice.mode,
        region_ids=choice.region_ids,
    )
