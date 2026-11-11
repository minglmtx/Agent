"""Independent literal/structural verification of one captured public window."""

from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.observation_read import ObservationReadPayload
from .observation_index import ObservationIndex


def verify_observation_read_window(
    index: ObservationIndex, window: ObservationReadPayload
) -> None:
    if window.request.snapshot != index.snapshot or window.overview != index.overview:
        raise EvidenceIntegrityError(
            "Local source changed original snapshot/current overview"
        )
    for fragment in window.fragments:
        if index.source(fragment.span) != fragment.text:
            raise EvidenceIntegrityError(
                "Local fragment is not the exact original source range"
            )
    for entry in window.directory:
        if (
            entry.region != index.region(entry.region.region_id)
            or index.source(entry.label_span) != entry.label_excerpt
        ):
            raise EvidenceIntegrityError(
                "Directory changed original object/label/parent/row identity"
            )
    for match in window.matches:
        if index.at(match.match_span.start).region_id != match.region_id:
            raise EvidenceIntegrityError(
                "Search match changed original row/code/comment context"
            )
        if (
            window.request.tool != "search_regions"
            or window.request.query.casefold()
            not in index.source(match.match_span).casefold()
        ):
            raise EvidenceIntegrityError(
                "Search result is not a literal original casefold match"
            )
    for mandatory in index.mandatory_context:
        if not any(
            fragment.span.start <= mandatory.span.start
            and mandatory.span.end <= fragment.span.end
            for fragment in window.fragments
        ):
            raise EvidenceIntegrityError(
                "Local view omitted necessary original modal/focus state"
            )
    # Header/row identities are original structural facts, not a task answer.
    for fragment in window.fragments:
        region = index.at(fragment.span.start)
        if region.kind == "table_row":
            for header in index.headers_for(region):
                if not any(
                    item.span.start <= header.start and header.end <= item.span.end
                    for item in window.fragments
                ):
                    raise EvidenceIntegrityError(
                        "Local row lost its original column-header mapping"
                    )
