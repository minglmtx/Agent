"""Reverse-check Q output against every original line, never render its output.

Audit coordinates are zero-based logical lines: /observation/text/lines/N and
/messages/1/content/ax/lines/N. Hashes include original line ends/indentation.
The frozen Q forward transformer is intentionally not imported here.
"""

import ast
import re
from lab_generate_skill.domain.context_transformation import (
    ContextChange,
    context_bytes_sha,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError

_ID = re.compile(r"^\[(\d+)\] ")
_EMPTY = re.compile(r"^\[\d+\] (row|rowgroup|paragraph) ''(?:\r?\n)?$")
_QUOTED = re.compile(r"(?:'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")")


def _labels(body: str) -> tuple[str, tuple[str, ...]]:
    role, _, tail = _ID.sub("", body.rstrip("\r\n")).partition(" ")
    result = []
    for value in (
        tail,
        tail.split("rendered_text=", 1)[1] if "rendered_text=" in tail else "",
    ):
        quoted = _QUOTED.match(value)
        if quoted is not None:
            text = ast.literal_eval(quoted.group())
            if type(text) is str:
                result.append(text)
    return role, tuple(result)


def diagnostic_changes(
    original: str, actual: str, complete_page: str, *, preserve_ids: bool = False
) -> tuple[ContextChange, ...]:
    """Allow only Q's exact layout, empty structure IDs and anchored duplicates."""
    if type(preserve_ids) is not bool:
        raise TypeError("Explicit boolean target ID strategy required")
    source = original.splitlines(keepends=True)
    target = actual.splitlines(keepends=True)
    stack: list[tuple[int, int, str, tuple[str, ...]]] = []
    changes = [
        ContextChange(
            operation="layout",
            source_path="/observation/text",
            target_path="/messages/1/content/ax",
            source_sha256=context_bytes_sha(original.encode()),
            target_sha256=context_bytes_sha(complete_page.encode()),
            related_source_paths=(),
            reason_code=(
                "MAP_ADDRESSABLE_LAYOUT_AND_SCOPE_V2"
                if preserve_ids
                else "Q_FROZEN_LAYOUT_AND_SCOPE"
            ),
        )
    ]
    seen: set[str] = set()
    current = 0
    for index, line in enumerate(source):
        depth = len(line) - len(line.lstrip("\t"))
        body = line[depth:]
        if body.startswith((" ", "\v", "\f")):
            raise EvidenceIntegrityError("Ambiguous original diagnostic indentation")
        bid = _ID.match(body)
        if bid is not None:
            if bid.group(1) in seen:
                raise EvidenceIntegrityError("Duplicate original diagnostic control ID")
            seen.add(bid.group(1))
        while stack and stack[-1][0] >= depth:
            stack.pop()
        normalized = "  " * depth + body
        expected_empty = "  " * depth + _ID.sub("", body)
        label_text = (
            body[len("StaticText ") :].rstrip("\r\n")
            if body.startswith("StaticText ")
            else ""
        )
        quoted = _QUOTED.fullmatch(label_text)
        label = ast.literal_eval(quoted.group()) if quoted is not None else None
        leaf = (
            index + 1 == len(source)
            or len(source[index + 1]) - len(source[index + 1].lstrip("\t")) <= depth
        )
        anchor = next(
            (
                parent
                for parent in reversed(stack)
                if parent[2] in ("gridcell", "columnheader", "rowheader", "generic")
                and label
                and label in parent[3]
            ),
            None,
        )
        if not preserve_ids and _EMPTY.fullmatch(body):
            if current >= len(target) or target[current] != expected_empty:
                raise EvidenceIntegrityError(
                    "Frozen Q view must remove empty structural IDs"
                )
            changes.append(
                ContextChange(
                    operation="remove_empty_id",
                    source_path=f"/observation/text/lines/{index}",
                    target_path=f"/messages/1/content/ax/lines/{current}",
                    source_sha256=context_bytes_sha(line.encode()),
                    target_sha256=context_bytes_sha(target[current].encode()),
                    related_source_paths=(),
                    reason_code="Q_EMPTY_UNADORNED_STRUCTURE",
                )
            )
            current += 1
        elif quoted is not None and leaf and anchor is not None:
            changes.append(
                ContextChange(
                    operation="omit_duplicate",
                    source_path=f"/observation/text/lines/{index}",
                    target_path=None,
                    source_sha256=context_bytes_sha(line.encode()),
                    target_sha256=None,
                    related_source_paths=(f"/observation/text/lines/{anchor[1]}",),
                    reason_code="Q_NONADDRESSABLE_LEAF_REPEATS_ANCESTOR",
                )
            )
        elif current < len(target) and target[current] == normalized:
            current += 1
        else:
            raise EvidenceIntegrityError(
                "Diagnostic view changed or omitted a protected original line"
            )
        role, labels = _labels(body)
        stack.append((depth, index, role, labels))
    if current != len(target):
        raise EvidenceIntegrityError(
            "Diagnostic view added unapproved lines or hierarchy"
        )
    return tuple(changes)
