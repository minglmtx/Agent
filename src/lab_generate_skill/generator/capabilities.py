"""Public actual Actor capability projection; no private or future task facts."""

import json
from pydantic import JsonValue
from lab_generate_skill.domain.browser_action_catalog import (
    ACTOR_OBSERVATION_MODE,
    declared_signatures,
)
from lab_generate_skill.domain.task import PublicTask
from .instructions import FULL_AX_GUIDANCE, VIEWPORT_GUIDANCE
from lab_generate_skill.domain.generator_actor_capabilities import (
    GeneratorActorCapabilities,
)


def actor_capabilities(
    task: PublicTask,
    initial_text: str,
    selected: GeneratorActorCapabilities | None = None,
) -> dict[str, JsonValue]:
    task = PublicTask.model_validate(task)
    if type(initial_text) is not str:
        raise TypeError("Exact initial public text required")
    signatures = declared_signatures(task.allowed_actions)
    try:
        value = json.loads(initial_text)
        scope = value.get("observation_scope") if type(value) is dict else None
    except ValueError:
        scope = None
    # The current Actor scaffold explicitly uses full AX. An opaque initial
    # body does not prove its own scope; these are deliberately separate facts.
    initial_scope = (
        "current_page_full_ax"
        if scope == FULL_AX_GUIDANCE
        else "viewport" if scope == VIEWPORT_GUIDANCE else "not_declared"
    )
    result: dict[str, JsonValue] = {
        "contract": "browsergym-actor-public-capabilities/1",
        "actor_observation_mode": ACTOR_OBSERVATION_MODE,
        "initial_observation_scope": initial_scope,
        "scope_limit": "Currently loaded page; no future pages or unloaded content.",
        "allowed_actions": list(signatures),
        "registered_read_tools": [],
        "id_rule": "Resolve IDs in the current Actor observation after a page change; never store an ID in a skill.",
    }
    if selected is not None:
        selected = GeneratorActorCapabilities.model_validate(selected)
        result.update(
            contract="browsergym-actor-public-capabilities/2",
            actor_observation_mode=selected.observation_mode,
            conditional_read_tools=list(selected.conditional_read_tools),
            read_limits=(
                None
                if selected.read_limits is None
                else selected.read_limits.model_dump(mode="json")
            ),
            availability="Use reads only when the actual current Actor input exposes the corresponding same-snapshot interface; this declares configured capability, not current tool registration or future page facts.",
        )
    return result
