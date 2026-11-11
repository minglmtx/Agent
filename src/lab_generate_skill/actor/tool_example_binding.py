"""Bind format examples to already-public bytes; no reads, actions or authority."""

import ast
from copy import deepcopy
import json
import re
from dataclasses import dataclass
from typing import Any

from lab_generate_skill.domain.actor_tool_definitions import TOOL_DEFINITIONS
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.policies.actor_tool_schemas import ActorToolSchemas
from .schema_response import schema_action
from .tool_schema_validation import actor_schema_violations


@dataclass(frozen=True)
class ExampleFacts:
    text: str
    url: str | None
    tab_index: int = 0

    def bids(self, *, clickable: bool = False) -> tuple[str, ...]:
        nodes = re.findall(
            r"^\s*\[([^\]\r\n]+)\] ([A-Za-z][A-Za-z_]*)(?: |$)", self.text, re.MULTILINE
        )
        roles = {
            "button",
            "link",
            "menuitem",
            "checkbox",
            "radio",
            "tab",
            "combobox",
            "treeitem",
        }
        return tuple(
            dict.fromkeys(
                bid
                for bid, role in nodes
                if role != "RootWebArea" and (not clickable or role in roles)
            )
        )

    def metadata(self) -> tuple[dict[str, Any], ...]:
        # Only renderer-owned metadata lines immediately following these headings.
        lines = self.text.splitlines()
        headings = {
            "# Original public current state",
            "# Current view",
            "# Public observation reading",
            "# Region directory (labels marked incomplete are excerpts)",
        }
        result = []
        for i, line in enumerate(lines):
            if line not in headings:
                continue
            j = i + (2 if line == "# Current view" else 1)
            if j >= len(lines):
                continue
            try:
                value = json.loads(lines[j])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                result.append(value)
            elif isinstance(value, list):
                result.extend(item for item in value if isinstance(item, dict))
        return tuple(result)


def action_format_example(
    name: str,
    task: PublicTask,
    schemas: ActorToolSchemas,
    facts: ExampleFacts,
    *,
    fields: tuple[str, ...] = (),
) -> tuple[dict[str, Any], bool]:
    """Boolean means public identifiers bound, never executable/goal-approved."""
    definition = schemas.require_tool(name, "browser_action")
    sample = definition["wire"]["example_response"]["action"]
    call = ast.parse(sample, mode="eval").body
    assert isinstance(call, ast.Call)
    order = definition["argument_order"]
    values = {key: ast.literal_eval(value) for key, value in zip(order, call.args)}
    values.update({key.arg: ast.literal_eval(key.value) for key in call.keywords})
    properties = definition["inputSchema"]["properties"]
    required = definition["inputSchema"].get("required", [])
    selected = [key for key in order if key in required or key in fields]
    bids = facts.bids(clickable=name in ("click", "dblclick"))
    bound = True
    for key in selected:
        if key in ("bid", "from_bid", "to_bid"):
            index = 1 if key == "to_bid" else 0
            values[key] = bids[index] if len(bids) > index else "<current_public_bid>"
            bound = bound and len(bids) > index
        elif key == "url":
            values[key] = facts.url or "<current_allowed_url>"
            bound = bound and facts.url is not None
        elif key == "index":
            values[key] = facts.tab_index
        elif key in ("options", "file"):
            values[key] = []  # Legal clearing form; no invented option/file.
        elif key not in values:
            values[key] = properties[key]["default"]
    example = dict(
        thought="Format only; not executed or a target recommendation.",
        action=f"{name}("
        + ", ".join(f"{key}={values[key]!r}" for key in selected)
        + ")",
    )
    # Even an explicitly unbound template must retain the real constructor/schema.
    schema_action(example, task, schemas, "format-example")
    return example, bound


def read_format_example(
    name: str,
    schemas: ActorToolSchemas,
    facts: ExampleFacts,
    *,
    unit: str = "whole_region",
    continuation: bool = False,
    original_request: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    definition = schemas.require_tool(name, "observation_read")
    properties = definition["inputSchema"]["properties"]
    read = dict(definition["wire"]["example_response"]["read"])
    read.update(
        snapshot_sha256=properties["snapshot_sha256"]["const"],
        output_tokens=min(1500, properties["output_tokens"]["maximum"]),
    )
    metadata = facts.metadata()
    bound = True
    if continuation:
        issued = next(
            (
                item["continuation_read"]
                for item in metadata
                if isinstance(item.get("continuation_read"), dict)
                and item["continuation_read"].get("tool") == name
            ),
            None,
        )
        if issued is not None:
            read = {"schema_version": "observation-read-choice/1", **issued}
        else:
            if original_request is not None:
                # This is an unbound template, never a repaired request. Preserve
                # every original query/range/output parameter instead of turning
                # a failed continuation into a different fresh read.
                read = {
                    "schema_version": "observation-read-choice/1",
                    **deepcopy(original_request),
                }
            elif name == "search_regions":
                read.update(query="<original_query>", region_ids=["<original_scope>"])
            read["continuation"] = "<issued_cursor_for_original_request>"
            bound = False
    if name == "read_region" and not continuation:
        regions = [
            item
            for item in metadata
            if isinstance(item.get("region"), str)
            and isinstance(item.get("source_span"), dict)
        ]
        if unit == "data_rows":
            regions = [
                item for item in regions if item.get("captured_data_rows", 0) > 0
            ]
        region = regions[0] if regions else None
        # A displayed full AX source proves its registered root region. A local
        # view without a suitable directory entry needs an explicit template.
        if (
            region is None
            and unit != "data_rows"
            and "# Complete captured accessibility text\n" in facts.text
        ):
            region = {"region": "ax-line-0"}
        selected = dict(
            region_id=region["region"] if region else "<current_region_id>", unit=unit
        )
        bound = bound and region is not None
        if unit != "whole_region":
            selected.update(start=0, end=1)
        read["ranges"] = [selected]
    if bound and actor_schema_violations(definition["inputSchema"], read):
        raise ValueError("Trusted read format example violates current schema")
    return dict(thought="Format only; this read was not executed.", read=read), bound
