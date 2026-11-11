"""Schema-built format examples for this task and its registered snapshot tools."""

import ast
import json
import re
from typing import Any
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn
from lab_generate_skill.domain.browser_action_catalog import (
    ACTIONS,
    declared_signatures,
)
from lab_generate_skill.domain.observation_read import ObservationRegionRange
from lab_generate_skill.domain.observation_read_choice import (
    ActorObservationReadChoice,
    ListObservationChoice,
    ReadObservationChoice,
    SearchObservationChoice,
)
from .response import parse_actor_action


def action_example(turn: ActorPublicTurn) -> dict[str, object]:
    source = turn.observation_source
    new = (
        source is not None
        and source.policy.schema_version == "observation-read-policy/2"
    )
    schemas = None
    if new:
        from lab_generate_skill.policies.actor_tool_schemas import (
            materialize_actor_tools,
        )

        assert source is not None
        schemas = materialize_actor_tools(
            turn.task.allowed_actions,
            source.tools,
            source.policy,
            source.snapshot.observation_ref.sha256,
            len(turn.observation.record.tabs),
        )
    else:
        declared_signatures(turn.task.allowed_actions)
    if new:
        from .tool_example_binding import ExampleFacts, action_format_example

        assert schemas is not None
        current = next(
            tab
            for tab in turn.observation.record.tabs
            if tab.tab_id == turn.observation.record.active_tab_id
        )
        facts = ExampleFacts(
            turn.observation.text or "",
            current.url,
            turn.observation.record.tabs.index(current),
        )
        names = sorted(
            turn.task.allowed_actions,
            key=lambda name: (
                name != "click",
                name in ("send_msg_to_user", "report_infeasible"),
                name,
            ),
        )
        for name in names:
            if name == "click" and not facts.bids(clickable=True):
                continue
            bound_example, bound = action_format_example(
                name, turn.task, schemas, facts
            )
            if bound:
                return bound_example
        raise ValueError("No complete action example can be bound to this public task")
    text = turn.observation.text or ""
    bids = re.findall(r"^\t*\[([0-9]+)\] ", text, re.MULTILINE)
    current = next(
        tab
        for tab in turn.observation.record.tabs
        if tab.tab_id == turn.observation.record.active_tab_id
    )
    values: dict[str, object] = {
        "text": "Report only verified observations.",
        "reason": "Explain a verified limitation.",
        "url": current.url,
        "index": next(
            i for i, tab in enumerate(turn.observation.record.tabs) if tab == current
        ),
        "delta_x": 0,
        "delta_y": 100,
        "value": "example",
        "options": "example",
        "key_comb": "Enter",
    }
    if new:
        values.update(file=[], options=[])
    if bids:
        values.update(bid=bids[0], from_bid=bids[0])
    if len(bids) > 1:
        values["to_bid"] = bids[1]
    names = sorted(
        turn.task.allowed_actions, key=lambda name: (name != "send_msg_to_user", name)
    )
    for name in names:
        if schemas is not None:
            definition = schemas.require_tool(name, "browser_action")
            required = definition["inputSchema"].get("required", [])
            arguments = tuple(
                str(key) for key in definition["argument_order"] if key in required
            )
            if any(key not in values for key in arguments):
                continue
            args = [repr(values[key]) for key in arguments]
        else:
            signature = ast.parse(ACTIONS[name], mode="eval").body
            if not isinstance(signature, ast.Call) or any(
                not isinstance(argument, ast.Name) or argument.id not in values
                for argument in signature.args
            ):
                continue
            args = [
                repr(values[argument.id])
                for argument in signature.args
                if isinstance(argument, ast.Name)
            ]
        example: dict[str, object] = dict(
            thought="Format example only; choose an operation from the actual goal and state.",
            action=f"{name}({', '.join(args)})",
        )
        # This validates trusted example construction, never repairs a model response.
        if schemas is not None:
            from .schema_response import schema_action

            schema_action(example, turn.task, schemas, "protocol-example")
        else:
            parse_actor_action(
                json.dumps(example), "stop", turn.task, "protocol-example"
            )
        return example
    raise ValueError("No complete action example can be bound to this public task")


def read_examples(turn: ActorPublicTurn) -> tuple[dict[str, object], ...]:
    source = turn.observation_source
    if source is None or not source.tools:
        return ()
    text = turn.observation.text
    if source.eligibility != "local_supported" or not text:
        raise ValueError(
            "Registered read examples require an actual captured AX source"
        )
    base: dict[str, Any] = dict(
        snapshot_sha256=source.snapshot.observation_ref.sha256,
        output_tokens=min(1500, source.policy.body_max_tokens),
        continuation=None,
    )
    result: list[dict[str, object]] = []
    for tool in source.tools:
        choice: ActorObservationReadChoice
        if tool == "list_regions":
            choice = ListObservationChoice(**base, parent_region_id=None)
        elif tool == "read_region":
            # The registered AX contract proves the original root region. Select
            # its complete opening line, without inventing a target or node ID.
            choice = ReadObservationChoice(
                **base,
                ranges=(
                    ObservationRegionRange(
                        region_id="ax-line-0",
                        unit="codepoints",
                        start=0,
                        end=len(text.splitlines(keepends=True)[0]),
                    ),
                ),
            )
        else:
            choice = SearchObservationChoice(
                **base, query="example text", region_ids=()
            )
        result.append(
            dict(
                thought="Format example only; this read has not been executed.",
                read=choice.model_dump(mode="json"),
            )
        )
        if source.policy.schema_version == "observation-read-policy/2":
            from lab_generate_skill.policies.actor_tool_schemas import (
                materialize_actor_tools,
            )
            from .tool_schema_validation import actor_schema_violations

            schemas = materialize_actor_tools(
                turn.task.allowed_actions,
                source.tools,
                source.policy,
                source.snapshot.observation_ref.sha256,
                len(turn.observation.record.tabs),
            )
            if actor_schema_violations(
                schemas.require_tool(tool, "observation_read")["inputSchema"],
                choice.model_dump(mode="json"),
            ):
                raise ValueError(
                    "Trusted current read example violates the effective tool schema"
                )
    return tuple(result)
