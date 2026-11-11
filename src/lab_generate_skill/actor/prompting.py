"""Baseline Actor full-AX projection; original bytes and scope are unchanged."""

from lab_generate_skill.domain.actor_prompt import ActorPublicTurn, ActorPrompt
from .message_layout import actor_messages


def prepare_actor(turn: ActorPublicTurn) -> ActorPrompt:
    turn = ActorPublicTurn.model_validate(turn)
    assert turn.observation.text is not None
    return ActorPrompt(messages=actor_messages(turn, turn.observation.text))
