"""Actual public framing; read names appear only for registered source tools."""

import json
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.browser_action_catalog import declared_signatures
from .instructions import system_instructions
from .history_layout import history_sections
from .protocol_examples import action_example, read_examples
from .tool_contract import fixed_tool_contract
from .proposal_correction import correction_example
from lab_generate_skill.domain.actor_proposal_feedback import ActorProposalFeedback


def adaptive_frame(turn: ActorPublicTurn) -> tuple[str, str, str]:
    source = turn.observation_source
    if source is None:
        raise OwnershipConflict("Explicit original public observation source required")
    if source.policy.schema_version == "observation-read-policy/2":
        return _schema_frame(turn)
    system = system_instructions(reads_registered=bool(source.tools))
    prefix = (
        "# Goal\n"
        + turn.task.goal
        + "\n\n# Applicable skills\n"
        + json.dumps(turn.skill.model_payload(), ensure_ascii=False)
        + "\n\n"
        + history_sections(turn)
        + "\n\n# Allowed business actions\n"
        + ", ".join(declared_signatures(turn.task.allowed_actions))
    )
    if turn.task.output_requirements:
        prefix += "\n\n# Public output requirements\n" + json.dumps(
            turn.task.output_requirements, ensure_ascii=False
        )
    prefix += "\n\n# Current public observation\n"
    if source.tools:
        system += (
            "\nRegistered readonly observation protocol: choose exactly one business action or one read proposal. "
            "A read has no website effect; it consumes this observation's shared read quota and a real generation. "
            "Return one JSON object with thought and action, or thought and read. Never combine operations using 'then' or a list. "
            "Read proposal fields: schema_version='observation-read-choice/1', tool, snapshot_sha256, output_tokens, continuation (or null). "
            "list_regions optionally takes parent_region_id. read_region takes a bounded ranges array of region_id/unit/start/end; "
            "unit is whole_region, data_rows, or codepoints. search_regions takes query, mode='unicode_casefold_literal/1', and region_ids (empty means captured snapshot). "
            "Search is literal casefold substring in this captured snapshot, not the whole website. "
            "Use exact original region/cursor identifiers from the current observation. "
            "For unknown region IDs, call list_regions before read_region. "
            "Rejected proposals execute no read and consume no read quota. Repeating an identical rejected proposal "
            "on the same snapshot stops this Actor at repeated_invalid_proposal_limit; executed-read no_progress is separate. "
            "One active reading window replaces the prior body; combine required ranges for comparison or reread a displaced range. "
            "Returned or included content does not prove you checked it. If information cannot be obtained within the declared quota, stop without guessing a business answer."
        )
        suffix = "\n\n# Registered observation tools and remaining quota\n" + json.dumps(
            {
                "tools": source.tools,
                "snapshot_sha256": source.snapshot.observation_ref.sha256,
                "reads_used": source.reads_used,
                "reads_remaining": source.policy.reads_per_observation
                - source.reads_used,
                "remaining_hint": source.policy.reads_per_observation
                - source.reads_used
                == source.policy.warn_remaining,
                "no_progress": source.no_progress,
                "no_progress_limit": source.policy.consecutive_no_progress,
                "repeated_invalid_proposal_limit": source.policy.consecutive_no_progress,
                "suggested_output_tokens": source.policy.body_target_tokens,
                "maximum_body_tokens": source.policy.body_max_tokens,
                "maximum_ranges": source.policy.max_ranges,
            },
            ensure_ascii=False,
        )
        suffix += "\n\nReturn exactly one JSON object with thought and either action or read. Use current IDs; do not infer actions from unread or unloaded content."
    else:
        suffix = "\n\nReturn exactly one JSON object with thought and action. Use one current allowed business action; do not combine multiple operations."
    suffix += (
        "\n\n# Complete format examples (not commands or observed results)\n"
        + json.dumps([action_example(turn), *read_examples(turn)], ensure_ascii=False)
    )
    return system, prefix, suffix


def _schema_frame(turn: ActorPublicTurn) -> tuple[str, str, str]:
    source = turn.observation_source
    assert source is not None and source.invalid_proposals is not None
    system = fixed_tool_contract(turn.task.allowed_actions, source.tools, source.policy)
    prefix = (
        "# Goal\n"
        + turn.task.goal
        + "\n\n# Applicable skills\n"
        + json.dumps(turn.skill.model_payload(), ensure_ascii=False)
    )
    if turn.task.output_requirements:
        prefix += "\n\n# Public output requirements\n" + json.dumps(
            turn.task.output_requirements, ensure_ascii=False
        )
    prefix += (
        "\n\n"
        + history_sections(
            turn,
            concise_rejections=True,
            latest_rejection=source.invalid_proposals.consecutive_invalid > 0,
        )
        + "\n\n# Current public observation\n"
    )
    suffix = ""
    if source.tools:
        remaining = source.policy.reads_per_observation - source.reads_used
        if remaining <= source.policy.warn_remaining:
            notice = (
                f"{remaining} read{'s remain' if remaining != 1 else ' remains'}. Use them for the remaining necessary information."
                if remaining
                else "No reads remain. Use displayed evidence or task-relevant controls; do not guess missing facts."
            )
            suffix = "\n\n# Reading notice\n" + notice
    corrected = None
    if (
        source.invalid_proposals.consecutive_invalid
        and turn.history
        and turn.history[-1].executed is False
    ):
        try:
            original_feedback = json.loads(turn.history[-1].error)
        except json.JSONDecodeError:
            original_feedback = None
        if (
            isinstance(original_feedback, dict)
            and original_feedback.get("status") == "proposal_rejected"
        ):
            feedback = ActorProposalFeedback.model_validate(original_feedback)
            corrected = correction_example(feedback) if feedback.can_correct else None
    examples = [] if corrected and "action" in corrected else [action_example(turn)]
    if source.reads_used < source.policy.reads_per_observation:
        for example in read_examples(turn):
            reading = example.get("read")
            if (
                corrected
                and "read" in corrected
                and isinstance(reading, dict)
                and reading["tool"] == corrected["read"]["tool"]
            ):
                continue
            examples.append(example)
    if examples:
        suffix += (
            "\n\n# Complete format examples (not commands or observed results)\n"
            + json.dumps(examples, ensure_ascii=False)
        )
    return system, prefix, suffix
