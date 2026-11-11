"""Narrow Rails diagnostic AX view; original complete observation stays authoritative.

Only duplicate non-addressable StaticText leaves and target IDs on empty,
unadorned structural rows/groups/paragraphs are omitted. Cell/control IDs and
attributes stay exact. Fixed space indentation preserves every retained depth.
"""

import ast
from dataclasses import dataclass
import re

_QUOTED = re.compile(r"(?:'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")")
_BID = re.compile(r"^\[(\d+)\] ")
_EMPTY_STRUCTURE = re.compile(r"^\[\d+\] (row|rowgroup|paragraph) ''(?:\r?\n)?$")


@dataclass(frozen=True)
class DiagnosticAxView:
    text: str
    duplicate_leaves: int
    structural_ids: int


def _description(body: str) -> tuple[str, tuple[str, ...]]:
    body = _BID.sub("", body)
    role, _, tail = body.partition(" ")
    values = []
    for text in (
        tail,
        tail.split("rendered_text=", 1)[1] if "rendered_text=" in tail else "",
    ):
        match = _QUOTED.match(text)
        if match is not None:
            value = ast.literal_eval(match.group())
            if isinstance(value, str):
                values.append(value)
    return role, tuple(values)


def diagnostic_ax_view(text: str, *, preserve_ids: bool = False) -> DiagnosticAxView:
    """Legacy defaults stay exact; explicit v2 preserves every target ID."""
    if type(preserve_ids) is not bool:
        raise TypeError("Explicit boolean target ID strategy required")
    if type(text) is not str or not text:
        raise ValueError("Complete nonempty original diagnostic AX required")
    lines = text.splitlines(keepends=True)
    if any(line.startswith((" ", "\v", "\f")) for line in lines):
        raise ValueError("Ambiguous original AX indentation")
    stack: list[tuple[int, str, tuple[str, ...]]] = []
    kept: list[str] = []
    before_ids: list[str] = []
    expected_ids: list[str] = []
    ids: set[str] = set()
    duplicate_leaves = structural_ids = 0
    for index, line in enumerate(lines):
        depth = len(line) - len(line.lstrip("\t"))
        body = line[depth:]
        if body.startswith((" ", "\v", "\f")):
            raise ValueError("Mixed original AX indentation")
        bid = _BID.match(body)
        if bid:
            if bid.group(1) in ids:
                raise ValueError("Duplicate original AX target ID")
            ids.add(bid.group(1))
            before_ids.append(body)
        while stack and stack[-1][0] >= depth:
            stack.pop()
        role, values = _description(body.rstrip("\r\n"))
        next_depth = (
            (len(lines[index + 1]) - len(lines[index + 1].lstrip("\t")))
            if index + 1 < len(lines)
            else -1
        )
        match = (
            _QUOTED.fullmatch(body[len("StaticText ") :].rstrip("\r\n"))
            if body.startswith("StaticText ")
            else None
        )
        if match is not None and next_depth <= depth:
            label = ast.literal_eval(match.group())
            if label and any(
                ancestor_role in ("gridcell", "columnheader", "rowheader", "generic")
                and label in labels
                for _, ancestor_role, labels in reversed(stack)
            ):
                duplicate_leaves += 1
                continue
        if not preserve_ids and _EMPTY_STRUCTURE.fullmatch(body):
            structural_ids += 1
            body = _BID.sub("", body)
        elif bid:
            expected_ids.append(body)
        kept.append("  " * depth + body)
        stack.append((depth, role, values))
    view = "".join(kept)
    after_ids = [
        line.lstrip(" ")
        for line in view.splitlines(keepends=True)
        if _BID.match(line.lstrip(" "))
    ]
    if (
        after_ids != expected_ids
        or len(before_ids) != len(expected_ids) + structural_ids
    ):
        raise ValueError("Diagnostic view changed named/control node IDs or attributes")
    return DiagnosticAxView(view, duplicate_leaves, structural_ids)
