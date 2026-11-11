"""Confirmed request mistakes against an already verified immutable index."""

import re
from collections.abc import Mapping
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.observation_read_progress import observation_request_key
from lab_generate_skill.domain.observation_read import (
    ObservationReadRequest,
    ReadObservationRegions,
    ListObservationRegions,
    SearchObservationRegions,
    ObservationRegion,
)
from .observation_index import ObservationIndex
from .actor_proposal_feedback import reject_proposal


def check_issued_continuation(
    request: ObservationReadRequest, bindings: Mapping[str, str]
) -> None:
    if request.continuation is None:
        return
    if not bindings:
        raise OwnershipConflict(
            "Original cursor mapping is unavailable; a new reader cannot recover it"
        )
    expected = observation_request_key(
        request.model_copy(update={"continuation": None})
    )
    if bindings.get(request.continuation) != expected:
        reject_proposal(
            "INVALID_CONTINUATION",
            "The cursor was not issued for these parameters by the current reader.",
            "Use the original issued cursor with unchanged snapshot/tool/query/ranges, or explicitly start a new read without a cursor.",
            tool=request.tool,
            field="continuation",
            actual=request.continuation,
            allowed="current reader-issued cursor and unchanged parameters",
        )


def _region(index: ObservationIndex, region_id: str, tool: str) -> ObservationRegion:
    match = re.fullmatch(r"ax-line-(0|[1-9][0-9]*)", region_id)
    if match is None or int(match.group(1)) >= len(index.regions):
        reject_proposal(
            "UNKNOWN_REGION",
            "region_id does not name a region in the current captured snapshot.",
            "Use a region_id from current public directory/search results, not an element bid or a constructed ID.",
            tool=tool,
            field="region_id",
            actual=region_id,
            allowed="current public region_ids",
        )
    region = index.region(region_id)
    if region.region_id != region_id:
        raise EvidenceIntegrityError(
            "Verified index returned a different region identity"
        )
    return region


def check_indexed_proposal(
    index: ObservationIndex, request: ObservationReadRequest
) -> None:
    index.require_snapshot(request.snapshot)
    if isinstance(request, ListObservationRegions):
        if request.parent_region_id is not None:
            _region(index, request.parent_region_id, request.tool)
    elif isinstance(request, SearchObservationRegions):
        for region_id in request.region_ids:
            _region(index, region_id, request.tool)
    elif isinstance(request, ReadObservationRegions):
        for selection in request.ranges:
            region = _region(index, selection.region_id, request.tool)
            if selection.unit == "whole_region":
                continue
            assert selection.start is not None and selection.end is not None
            length = (
                len(region.data_row_spans)
                if selection.unit == "data_rows"
                else region.span.end - region.span.start
            )
            if (
                selection.unit == "data_rows" and region.kind != "table"
            ) or not 0 <= selection.start < selection.end <= length:
                reject_proposal(
                    "RANGE_OUT_OF_BOUNDS",
                    "The requested range is unavailable in this captured region.",
                    "Use a zero-based nonempty half-open range; data_rows applies only to table data and excludes headers.",
                    tool=request.tool,
                    field="ranges",
                    actual={
                        "region_id": selection.region_id,
                        "unit": selection.unit,
                        "start": selection.start,
                        "end": selection.end,
                    },
                    allowed={"kind": region.kind, "start": 0, "end_maximum": length},
                )
