"""The unchanged Actor message scaffold; selected projectors supply public page text."""

import json
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn, ActorMessage
from .instructions import SYSTEM
from .history_layout import history_sections
from lab_generate_skill.domain.browser_action_catalog import declared_signatures


def actor_messages(
    turn: ActorPublicTurn, page_text: str
) -> tuple[ActorMessage, ActorMessage]:
    turn = ActorPublicTurn.model_validate(turn)
    if type(page_text) is not str:
        raise ValueError("Explicit public page text string required")
    signatures = declared_signatures(turn.task.allowed_actions)
    observation = turn.observation.record
    current = next(
        tab for tab in observation.tabs if tab.tab_id == observation.active_tab_id
    )
    history = (
        "# Previous actions\n"
        + json.dumps([h.model_dump() for h in turn.history], ensure_ascii=False)
        if all(item.executed is None for item in turn.history)
        else history_sections(turn)
    )
    content = (
        f"# Goal\n{turn.task.goal}\n\n# Current URL\n{current.url}"
        f"\n\n# Current page accessibility tree\n{page_text}"
        f"\n\n{history}"
        f"\n\n# Last action error\n{observation.last_action_error}"
        f"\n\n# Allowed actions\n{', '.join(signatures)}. "
        "Use element IDs from the current tree; IDs are strings."
        "\n\n# Open tabs\n"
        + json.dumps(
            [
                {
                    "index": i,
                    "url": t.url,
                    "title": t.title,
                    "active": t.tab_id == observation.active_tab_id,
                }
                for i, t in enumerate(observation.tabs)
            ],
            ensure_ascii=False,
        )
    )
    if turn.task.output_requirements:
        content += "\n\n# Public output requirements\n" + json.dumps(
            turn.task.output_requirements, ensure_ascii=False
        )
    content += "\n\n# Applicable skills\n" + json.dumps(
        turn.skill.model_payload(), ensure_ascii=False
    )
    content += "\n\nReturn one JSON object with thought and action. Element IDs come from [bid] in the current tree."
    return (
        ActorMessage(role="system", content=SYSTEM),
        ActorMessage(role="user", content=content),
    )
