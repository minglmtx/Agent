"""Literal casefold search within an immutable public structure, never a website.

Offsets of expanded casefold text map back to original codepoints. Pagination
reports inspected coverage separately from displayed hits; source rows/objects
with equal text are never merged. Actual tool quotas/permissions belong outside.
"""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from lab_generate_skill.domain.observation_read import ObservationSourceSpan
from .observation_index import ObservationIndex


@dataclass(frozen=True)
class ObservationSearchHit:
    match_span: ObservationSourceSpan
    region_id: str


@dataclass(frozen=True)
class ObservationSearchPage:
    hits: tuple[ObservationSearchHit, ...]
    requested_coverage: tuple[ObservationSourceSpan, ...]
    inspected_coverage: tuple[ObservationSourceSpan, ...]
    coverage_complete: bool
    results_exhausted: bool
    # Internal coordinate only. The adapter must issue a scoped opaque cursor;
    # this number is neither a public tool cursor nor resumption authority.
    next_folded_offset: int | None


@dataclass(frozen=True)
class ObservationSearchIndex:
    source: ObservationIndex
    folded_text: str
    prefix: tuple[int, ...]


def index_literal_search(index: ObservationIndex) -> ObservationSearchIndex:
    prefix = [0]
    parts = []
    for character in index.text:
        folded = character.casefold()
        parts.append(folded)
        prefix.append(prefix[-1] + len(folded))
    return ObservationSearchIndex(index, "".join(parts), tuple(prefix))


def literal_search(
    index: ObservationIndex,
    query: str,
    region_ids: tuple[str, ...],
    *,
    after_folded_offset: int = 0,
    max_hits: int | None = None,
    prepared: ObservationSearchIndex | None = None,
) -> ObservationSearchPage:
    if type(query) is not str or not 0 < len(query) <= 256:
        raise ValueError("One nonempty bounded literal public query required")
    query.encode("utf-8")
    if (
        type(region_ids) is not tuple
        or len(set(region_ids)) != len(region_ids)
        or len(region_ids) > 128
    ):
        raise ValueError("Explicit unique public search regions required")
    if type(after_folded_offset) is not int or after_folded_offset < 0:
        raise ValueError("Original validated internal search coordinate required")
    if not index.regions:
        if region_ids or after_folded_offset:
            raise ValueError("Empty observation has no region or continuation")
        return ObservationSearchPage((), (), (), True, True, None)
    requested = (
        sorted(
            (index.region(r).span for r in region_ids), key=lambda s: (s.start, s.end)
        )
        if region_ids
        else [ObservationSourceSpan(start=0, end=len(index.text))]
    )
    merged: list[ObservationSourceSpan] = []
    for span in requested:
        if merged and span.start <= merged[-1].end:
            merged[-1] = ObservationSourceSpan(
                start=merged[-1].start, end=max(span.end, merged[-1].end)
            )
        else:
            merged.append(span)
    if max_hits is not None and (
        type(max_hits) is not int or not 1 <= max_hits <= index.policy.search_hits
    ):
        raise ValueError("Search page hit cap exceeds original frozen boundary")
    hit_limit = index.policy.search_hits if max_hits is None else max_hits
    prepared = index_literal_search(index) if prepared is None else prepared
    if prepared.source is not index:
        raise ValueError("Search index is not this original immutable snapshot")
    prefix, folded_text, needle = (
        prepared.prefix,
        prepared.folded_text,
        query.casefold(),
    )
    if not needle or after_folded_offset > len(folded_text):
        raise ValueError("Unavailable literal search continuation")
    hits: list[ObservationSearchHit] = []
    seen: set[ObservationSourceSpan] = set()
    inspected = []
    last_end = 0
    for span in merged:
        begin = max(prefix[span.start], after_folded_offset)
        end = prefix[span.end]
        if begin >= end:
            continue
        position = begin
        while True:
            at = folded_text.find(needle, position, end)
            if at < 0:
                start = max(span.start, bisect_right(prefix, begin) - 1)
                if start < span.end:
                    inspected.append(ObservationSourceSpan(start=start, end=span.end))
                break
            source_span = ObservationSourceSpan(
                start=bisect_right(prefix, at) - 1,
                end=bisect_left(prefix, at + len(needle)),
            )
            # Preserve overlapping matches at distinct original characters,
            # without returning two aliases of one expanded casefold character.
            position = max(at + 1, prefix[source_span.start + 1])
            if source_span in seen:
                continue  # Two folded letters from one original codepoint.
            seen.add(source_span)
            if len(hits) == hit_limit:
                start = max(span.start, bisect_right(prefix, begin) - 1)
                if start < source_span.end:
                    inspected.append(
                        ObservationSourceSpan(start=start, end=source_span.end)
                    )
                return ObservationSearchPage(
                    tuple(hits), tuple(merged), tuple(inspected), False, False, last_end
                )
            hits.append(
                ObservationSearchHit(source_span, index.at(source_span.start).region_id)
            )
            last_end = position
    return ObservationSearchPage(
        tuple(hits), tuple(merged), tuple(inspected), True, True, None
    )
