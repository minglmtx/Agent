"""Render explicit execution facts; never infer execution from proposal text."""

import json
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn
from lab_generate_skill.domain.actor_proposal_feedback import ActorProposalFeedback


def history_sections(
    turn: ActorPublicTurn,
    *,
    concise_rejections: bool = False,
    latest_rejection: bool = True,
) -> str:
    actions = []
    rejected = []
    legacy = []
    for index, item in enumerate(turn.history):
        if item.executed is True:
            actions.append(dict(action=item.action, error=item.error, executed=True))
        elif item.executed is False:
            rejected.append(
                dict(
                    **({} if concise_rejections else {"proposal": item.action}),
                    status="proposal_rejected",
                    executed=False,
                    feedback=(
                        _concise_feedback(
                            item.error,
                            latest=latest_rejection and index == len(turn.history) - 1,
                        )
                        if concise_rejections
                        else item.error
                    ),
                )
            )
        else:
            legacy.append(item.model_dump())
    result = (
        "# Previous executed business actions\n"
        + json.dumps(actions, ensure_ascii=False)
        + "\n\n# Rejected proposals: not executed, not search results\n"
        + json.dumps(rejected, ensure_ascii=False)
    )
    if legacy:
        result += (
            "\n\n# Legacy history: execution status was not explicitly recorded\n"
            + json.dumps(legacy, ensure_ascii=False)
        )
    return result


def _concise_feedback(message: str, *, latest: bool) -> str | dict[str, object]:
    # Preserve legacy feedback as data. Recognized structured feedback must
    # validate; malformed persisted facts are never converted into a retry.
    try:
        value = json.loads(message)
    except json.JSONDecodeError:
        return message
    if not isinstance(value, dict) or value.get("status") != "proposal_rejected":
        return message
    feedback = ActorProposalFeedback.model_validate_json(message)
    if not latest:
        return dict(tool=feedback.tool, code=feedback.code, executed=False)
    return {
        key: value
        for key, value in feedback.model_dump().items()
        if key
        in ("tool", "code", "message", "field", "actual", "allowed", "next_action")
        and value is not None
    }
