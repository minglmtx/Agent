"""Exact displayed coordinates and coverage facts, never model understanding."""

import hashlib
import json
from typing import Literal
from .observation_read import ObservationReadPayload, ObservationSourceSpan

ObservationProgressKind = Literal[
    "content_ranges", "directory_coverage", "search_coverage"
]


def reading_display_spans(
    payload: ObservationReadPayload,
) -> tuple[ObservationSourceSpan, ...]:
    return tuple(
        sorted(
            set(
                (
                    *[fragment.span for fragment in payload.fragments],
                    *[entry.label_span for entry in payload.directory],
                )
            ),
            key=lambda span: (span.start, span.end),
        )
    )


def reading_progress_kind(payload: ObservationReadPayload) -> ObservationProgressKind:
    return (
        "directory_coverage"
        if payload.request.tool == "list_regions"
        else (
            "search_coverage"
            if payload.request.tool == "search_regions"
            else "content_ranges"
        )
    )


def reading_progress_fingerprint(payload: ObservationReadPayload) -> str:
    request = payload.request
    facts: dict[str, object] = {
        "snapshot": request.snapshot.model_dump(mode="json"),
        "tool": request.tool,
        "displayed_spans": [
            span.model_dump() for span in reading_display_spans(payload)
        ],
        "coverage": [span.model_dump() for span in payload.covered_ranges],
        "complete": payload.complete,
        "search_coverage_complete": payload.search_coverage_complete,
        "results_exhausted": payload.results_exhausted,
        "directory": [
            (
                entry.region.region_id,
                entry.label_span.model_dump(),
                entry.label_complete,
            )
            for entry in payload.directory
        ],
        "matches": [match.model_dump() for match in payload.matches],
    }
    if request.tool == "list_regions":
        facts["parent_region_id"] = request.parent_region_id
    if request.tool == "search_regions":
        facts.update(
            query=request.query, matching=request.mode, region_ids=request.region_ids
        )
    # Logical IDs, output quotas and opaque cursor spellings cannot fabricate
    # progress. Actual inspected/displayed ranges and query/parent scope do.
    return hashlib.sha256(
        json.dumps(
            facts, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def ranges_already_displayed(
    current: tuple[ObservationSourceSpan, ...],
    requested: tuple[ObservationSourceSpan, ...],
) -> bool:
    merged: list[tuple[int, int]] = []
    for span in sorted(current, key=lambda span: (span.start, span.end)):
        if merged and span.start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], span.end))
        else:
            merged.append((span.start, span.end))
    return bool(requested) and all(
        any(start <= span.start and span.end <= end for start, end in merged)
        for span in requested
    )
