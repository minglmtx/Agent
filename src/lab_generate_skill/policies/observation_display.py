"""One public reading body's readable framing, shared with reverse verification.

No context/skill/history, model request, website operation or private engineering
state enters this formatter. Body tokens still require the actual native count.
"""

import json
from typing import Literal
from lab_generate_skill.domain.observation_read import ObservationReadPayload
from lab_generate_skill.domain.observation_read_geometry import reading_display_spans


def observation_read_body(
    payload: ObservationReadPayload,
    *,
    current_view: Literal["structural_local", "viewport_priority"] | None = None,
    captured_length: int | None = None,
    read_tools: tuple[str, ...] = (),
) -> str:
    payload = ObservationReadPayload.model_validate(payload)
    snapshot = payload.request.snapshot
    metadata: dict[str, object] = {
        "snapshot": snapshot.observation_ref.sha256,
        "observation_version": snapshot.observation_version,
        "tab": snapshot.tab_id,
        "frame": snapshot.frame_id,
        "scope": "Current captured public snapshot only; unloaded website pages are unknown.",
        "complete_requested_range": payload.complete,
        "search_coverage_complete": payload.search_coverage_complete,
        "results_exhausted": payload.results_exhausted,
        "continuation": payload.continuation,
        "omissions": payload.omissions,
        "covered_ranges": [span.model_dump() for span in payload.covered_ranges],
    }
    if payload.overview is not None:
        metadata["original_public_overview"] = payload.overview.model_dump(mode="json")
    if payload.request.tool == "search_regions":
        metadata.update(query=payload.request.query, matching=payload.request.mode)
    if payload.request.tool == "list_regions":
        metadata.update(
            directory_parent_region=payload.request.parent_region_id,
            directory_scope="Captured structural entry points; use parent_region_id for direct children, or literal search/read ranges. This is not every AX node or unloaded page.",
        )
    if current_view is None:
        if captured_length is not None or read_tools:
            raise ValueError(
                "Current-view coverage requires an explicit display version"
            )
        lines = ["# Public observation reading"]
    else:
        if type(captured_length) is not int or captured_length < 1 or not read_tools:
            raise ValueError(
                "Local display requires actual captured extent and registered readers"
            )
        if payload.continuation is not None:
            continuation = payload.request.model_dump(
                mode="json",
                exclude={"snapshot", "schema_version", "request_id", "continuation"},
                exclude_none=True,
            )
            continuation.update(
                snapshot_sha256=snapshot.observation_ref.sha256,
                continuation=payload.continuation,
            )
            metadata["continuation_read"] = continuation
        displayed = reading_display_spans(payload)
        missing = []
        position = 0
        for span in displayed:
            if span.end > captured_length:
                raise ValueError("Displayed range left captured source")
            if span.start > position:
                missing.append([position, span.start])
            position = max(position, span.end)
        if position < captured_length:
            missing.append([position, captured_length])
        metadata.pop("scope")
        metadata["snapshot_sha256"] = metadata.pop("snapshot")
        metadata["displayed"] = (
            "Original source fragments and directory labels below; each carries its exact source coordinates."
        )
        metadata["captured_but_unshown"] = {
            "unit": "unicode_codepoints",
            "ranges": missing[:16],
            "range_count": len(missing),
            "all_ranges_listed": len(missing) <= 16,
            "available_tools": read_tools,
        }
        metadata["uncaptured_or_pending"] = "unknown"
        description = (
            "Viewport-priority local view with necessary structural context; not every included element is on screen. After scrolling, use the new observation."
            if current_view == "viewport_priority"
            else "Structural local view, neither complete text nor the screen-visible area; omitted captured content is described below."
        )
        lines = ["# Current view", description]
    lines.append(json.dumps(metadata, ensure_ascii=False, separators=(",", ":")))
    if payload.directory:
        entries = [
            dict(
                region=item.region.region_id,
                kind=item.region.kind,
                source_span=item.region.span.model_dump(),
                parent=item.region.parent_region_id,
                captured_data_rows=len(item.region.data_row_spans),
                label_excerpt=item.label_excerpt,
                label_complete=item.label_complete,
            )
            for item in payload.directory
        ]
        lines.extend(
            (
                "# Region directory (labels marked incomplete are excerpts)",
                json.dumps(entries, ensure_ascii=False, separators=(",", ":")),
            )
        )
    if payload.matches:
        lines.extend(
            (
                "# Literal matches in inspected source ranges",
                json.dumps(
                    [match.model_dump() for match in payload.matches],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
        )
    for fragment in payload.fragments:
        span = fragment.span
        lines.extend(
            (
                f"# Original source [{span.start},{span.end}) {span.unit}; {fragment.purpose}",
                fragment.text,
            )
        )
    if not payload.fragments and not payload.directory:
        lines.append(
            "No displayed content in this returned range. See coverage and continuation; this is not absence across the website."
        )
    return "\n".join(lines)
