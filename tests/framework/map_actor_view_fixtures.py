"""Exact retained public inputs, no live source/model/resource authority."""

import json
from pathlib import Path
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_prompt import (
    ActorPublicTurn,
    ActorHistoryItem,
    ActorPrompt,
)
from lab_generate_skill.domain.observation import Observation, ResolvedObservation

ROOT = Path(__file__).with_name("fixtures")


def original_request() -> ActorRunRequest:
    return ActorRunRequest.model_validate_json(
        (ROOT / "map-actor-budget-request.json").read_bytes()
    )


def original_turn(index: int | None = None) -> tuple[ActorPublicTurn, ActorPrompt]:
    suffix = "failed-prompt" if index is None else "prompt-" + str(index)
    prompt = ActorPrompt.model_validate_json(
        (ROOT / ("map-actor-budget-" + suffix + ".json")).read_bytes()
    )
    suffix = "failed-observation" if index is None else "observation-" + str(index)
    observation = Observation.model_validate_json(
        (ROOT / ("map-actor-budget-" + suffix + ".json")).read_bytes()
    )
    user = prompt.messages[1].content
    history = json.loads(
        user.split("# Previous actions\n", 1)[1].split("\n\n# Last action error", 1)[0]
    )
    request = original_request()
    return (
        ActorPublicTurn(
            task=request.task,
            skill=request.skill,
            memory=request.memory,
            observation=ResolvedObservation(record=observation, text=observation.text),
            history=tuple(ActorHistoryItem.model_validate(item) for item in history),
        ),
        prompt,
    )
