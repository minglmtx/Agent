"""Instantiate the one program-side catalog; no tools or permissions are added."""

import copy
from dataclasses import dataclass
from typing import Any
from lab_generate_skill.domain.actor_tool_definitions import (
    TOOL_DEFINITIONS,
    RESPONSE_ENVELOPE,
    CATALOG_SHA256,
)
from lab_generate_skill.domain.observation_read_policy import ObservationReadPolicy


@dataclass(frozen=True)
class ActorToolSchemas:
    catalog_sha256: str
    tools: tuple[dict[str, Any], ...]
    envelope: dict[str, Any]

    def require_tool(self, name: str, branch: str) -> dict[str, Any]:
        matches = [
            tool
            for tool in self.tools
            if tool["name"] == name and tool["kind"] == branch
        ]
        if len(matches) != 1:
            raise ValueError("Exactly one actual registered tool required")
        return matches[0]


def materialize_actor_tools(
    allowed_actions: tuple[str, ...],
    read_tools: tuple[str, ...],
    policy: ObservationReadPolicy,
    snapshot_sha256: str,
    tab_count: int,
) -> ActorToolSchemas:
    if type(tab_count) is not int or tab_count < 1:
        raise ValueError("Current ready observation requires at least one tab")
    if len(snapshot_sha256) != 64 or any(
        c not in "0123456789abcdef" for c in snapshot_sha256
    ):
        raise ValueError("Original current public observation hash required")
    if len(set(allowed_actions)) != len(allowed_actions) or len(set(read_tools)) != len(
        read_tools
    ):
        raise ValueError("Distinct actual registered tool names required")
    tools = []
    for names, kind in (
        (allowed_actions, "browser_action"),
        (read_tools, "observation_read"),
    ):
        for name in names:
            if name not in TOOL_DEFINITIONS or TOOL_DEFINITIONS[name]["kind"] != kind:
                raise ValueError("Tool set differs from declared registration")
            tool = copy.deepcopy(TOOL_DEFINITIONS[name])
            properties = tool["inputSchema"]["properties"]
            if kind == "observation_read":
                properties["snapshot_sha256"]["const"] = snapshot_sha256
                properties["output_tokens"]["maximum"] = min(
                    61440, policy.body_max_tokens
                )
                if name == "read_region":
                    properties["ranges"]["maxItems"] = policy.max_ranges
            elif name == "tab_focus":
                properties["index"]["maximum"] = tab_count - 1
            tools.append(tool)
    envelope = copy.deepcopy(RESPONSE_ENVELOPE)
    if read_tools:
        envelope["oneOf"][1]["properties"]["read"] = {
            "oneOf": [
                copy.deepcopy(t["inputSchema"])
                for t in tools
                if t["kind"] == "observation_read"
            ]
        }
    else:
        envelope["oneOf"] = [envelope["oneOf"][0]]
    return ActorToolSchemas(CATALOG_SHA256, tuple(tools), envelope)
