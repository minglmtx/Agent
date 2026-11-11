"""Finite structural pages from one public source; token fit remains external."""

from dataclasses import dataclass
from lab_generate_skill.domain.observation_read import (
    ListObservationRegions,
    ReadObservationRegions,
    SearchObservationRegions,
    ObservationReadRequest,
    ObservationReadPayload,
    ObservationRegionRange,
    ObservationSourceSpan,
    ObservationDirectoryEntry,
    ObservationSearchMatch,
    ObservationReadFragment,
    ObservationRegion,
)
from .observation_index import ObservationIndex
from .observation_search import ObservationSearchIndex, literal_search


@dataclass(frozen=True)
class ObservationPage:
    payload: ObservationReadPayload
    next_offset: int | None


def directory_regions(
    index: ObservationIndex, parent_region_id: str | None
) -> tuple[ObservationRegion, ...]:
    """Structural entry points, or an explicit original parent's direct children.

    The default is a directory of captured public structure, not one entry per
    AX line. Nothing is merged by label or claimed to be the whole website.
    Every omitted subtree remains addressable by original range/search.
    """
    if parent_region_id is not None:
        parent = index.region(parent_region_id)
        return tuple(
            region
            for region in index.regions
            if region.parent_region_id == parent.region_id
        )
    if not index.regions:
        return ()
    landmarks = {
        "navigation",
        "main",
        "banner",
        "contentinfo",
        "search",
        "form",
        "region",
        "dialog",
        "alert",
        "alertdialog",
        "tabpanel",
        "tree",
        "list",
    }
    selected = []
    for node, region in zip(index.nodes, index.regions, strict=True):
        direct = node.parent == 0
        ancestor = node.parent
        nested_structure = False
        while ancestor is not None:
            if index.regions[ancestor].kind in (
                "table",
                "table_row",
                "code",
                "comment",
            ):
                nested_structure = True
                break
            ancestor = index.nodes[ancestor].parent
        if (
            node.line == 0
            or direct
            or (
                not nested_structure
                and (
                    node.role in landmarks
                    or region.kind in ("table", "code", "comment")
                )
            )
        ):
            selected.append(region)
    # Publish global structured entry points before potentially long navigation
    # directories. Original labels/identities/spans stay exact; this ordering
    # uses no task query, private answer or predicted target.
    return tuple(
        sorted(
            selected,
            key=lambda region: (
                (
                    0
                    if region.region_id == "ax-line-0"
                    else 1 if region.kind in ("table", "code", "comment") else 2
                ),
                region.span.start,
            ),
        )
    )


def read_units(
    index: ObservationIndex, request: ReadObservationRegions
) -> tuple[tuple[str, ObservationSourceSpan], ...]:
    if len(request.ranges) > index.policy.max_ranges:
        raise ValueError("Requested multi-range read exceeds original shared boundary")
    units = []
    for selection in request.ranges:
        for span in index.selected_spans(selection):
            # Original explicit codepoint selections may be partial. Automatic
            # page boundaries retain whole rows/code/comments, never a prefix
            # of a cell or a syntactically plausible chopped action parameter.
            if selection.unit == "codepoints":
                units.append((selection.region_id, span))
                continue
            position = span.start
            while position < span.end:
                region = index.at(position)
                end = (
                    region.span.end
                    if region.kind in ("table_row", "code", "comment")
                    else region.opening_span.end
                )
                end = min(span.end, end)
                if end <= position:
                    raise ValueError(
                        "Public structure did not advance its original range"
                    )
                units.append(
                    (
                        selection.region_id,
                        ObservationSourceSpan(start=position, end=end),
                    )
                )
                position = end
    return tuple(units)


def observation_page(
    index: ObservationIndex,
    request: ObservationReadRequest,
    *,
    offset: int,
    limit: int,
    next_cursor: str,
    search: ObservationSearchIndex,
) -> ObservationPage:
    index.require_snapshot(request.snapshot)
    if type(offset) is not int or offset < 0 or type(limit) is not int or limit < 1:
        raise ValueError("Explicit bounded page coordinates required")
    fragments: tuple[ObservationReadFragment, ...] = ()
    directory: tuple[ObservationDirectoryEntry, ...] = ()
    matches: tuple[ObservationSearchMatch, ...] = ()
    coverage: tuple[ObservationSourceSpan, ...] = ()
    search_complete: bool | None = None
    omissions: tuple[str, ...] = ()
    next_offset = None
    if isinstance(request, ListObservationRegions):
        listed_regions = directory_regions(index, request.parent_region_id)
        if limit > index.policy.directory_entries or offset > len(listed_regions):
            raise ValueError("Directory page exceeds original frozen source")
        selected = listed_regions[offset : offset + limit]
        entries = []
        for region in selected:
            opening = region.opening_span
            label_span = ObservationSourceSpan(
                start=opening.start, end=min(opening.end, opening.start + 512)
            )
            entries.append(
                ObservationDirectoryEntry(
                    region=region,
                    label_span=label_span,
                    label_excerpt=index.source(label_span),
                    label_complete=label_span == opening,
                )
            )
        directory = tuple(entries)
        coverage = tuple(item.label_span for item in directory)
        if offset + len(selected) < len(listed_regions):
            next_offset = offset + len(selected)
            omissions = ("directory_remaining",)
        if any(not entry.label_complete for entry in directory):
            omissions += ("directory_label_excerpts",)
    elif isinstance(request, ReadObservationRegions):
        if limit > index.policy.page_units:
            raise ValueError("Read page exceeds its auxiliary structural-unit boundary")
        units = read_units(index, request)
        if offset >= len(units):
            raise ValueError("Read continuation is outside original requested ranges")
        selected_units = units[offset : offset + limit]
        selections: list[ObservationRegionRange] = []
        for region_id, span in selected_units:
            region = index.region(region_id)
            if (
                selections
                and selections[-1].region_id == region_id
                and selections[-1].end == span.start - region.span.start
            ):
                previous = selections[-1]
                selections[-1] = ObservationRegionRange(
                    region_id=region_id,
                    unit="codepoints",
                    start=previous.start,
                    end=span.end - region.span.start,
                )
            else:
                selections.append(
                    ObservationRegionRange(
                        region_id=region_id,
                        unit="codepoints",
                        start=span.start - region.span.start,
                        end=span.end - region.span.start,
                    )
                )
        fragments = index.fragments(tuple(selections))
        coverage = tuple(span for _, span in selected_units)
        if offset + len(selected_units) < len(units):
            next_offset = offset + len(selected_units)
            omissions = ("requested_ranges_remaining",)
    else:
        assert isinstance(request, SearchObservationRegions)
        page = literal_search(
            index,
            request.query,
            request.region_ids,
            after_folded_offset=offset,
            max_hits=limit,
            prepared=search,
        )
        regions = tuple(dict.fromkeys(hit.region_id for hit in page.hits))
        if regions:
            fragments = index.fragments(
                tuple(
                    ObservationRegionRange(region_id=r, unit="whole_region")
                    for r in regions
                )
            )
        matches = tuple(
            ObservationSearchMatch(match_span=hit.match_span, region_id=hit.region_id)
            for hit in page.hits
        )
        coverage = page.inspected_coverage
        search_complete = page.coverage_complete
        next_offset = page.next_folded_offset
        if not page.results_exhausted:
            omissions = ("search_results_and_coverage_remaining",)
    exhausted = next_offset is None
    combined = list(fragments)
    for mandatory in index.mandatory_fragments():
        if any(
            fragment.span.start <= mandatory.span.start
            and mandatory.span.end <= fragment.span.end
            for fragment in combined
        ):
            continue
        combined = [
            fragment
            for fragment in combined
            if not (
                mandatory.span.start <= fragment.span.start
                and fragment.span.end <= mandatory.span.end
            )
        ]
        combined.append(mandatory)
    fragments = tuple(
        sorted(combined, key=lambda fragment: (fragment.span.start, fragment.span.end))
    )
    payload = ObservationReadPayload(
        schema_version="observation-read-result/2",
        overview=index.overview,
        request=request,
        fragments=fragments,
        covered_ranges=coverage,
        complete=exhausted and not omissions,
        search_coverage_complete=search_complete,
        results_exhausted=exhausted,
        omissions=omissions,
        continuation=None if exhausted else next_cursor,
        directory=directory,
        matches=matches,
    )
    return ObservationPage(payload, next_offset)
