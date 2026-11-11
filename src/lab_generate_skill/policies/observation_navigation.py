"""Preferred complete captured navigation; token fit belongs to native selection."""

from lab_generate_skill.domain.observation_read import (
    ObservationReadPayload,
    ObservationRegionRange,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from .observation_index import ObservationIndex
from .observation_protection import verify_observation_read_window

_NAVIGATION = frozenset(("navigation", "menubar", "menu"))


def with_complete_navigation(
    index: ObservationIndex, original: ObservationReadPayload
) -> ObservationReadPayload:
    """No goal/answer/visibility heuristic; use actual public subtree coordinates."""
    verify_observation_read_window(index, original)
    if (
        original.request.tool != "list_regions"
        or original.request.parent_region_id is not None
        or original.request.continuation is not None
    ):
        raise OwnershipConflict(
            "Only the original automatic initial directory qualifies"
        )
    fragments = {item.span: item for item in original.fragments}
    for node in index.nodes:
        if node.role not in _NAVIGATION:
            continue
        parent = node.parent
        while parent is not None and index.nodes[parent].role not in _NAVIGATION:
            parent = index.nodes[parent].parent
        if parent is not None:
            continue  # Its complete captured navigation ancestor already contains it.
        for item in index.fragments(
            (
                ObservationRegionRange(
                    region_id=f"ax-line-{node.line}", unit="whole_region"
                ),
            )
        ):
            fragments.setdefault(item.span, item)
    selected = tuple(
        item
        for item in fragments.values()
        if not any(
            other.span != item.span
            and other.span.start <= item.span.start
            and item.span.end <= other.span.end
            for other in fragments.values()
        )
    )
    result = ObservationReadPayload.model_validate(
        original.model_copy(
            update={
                "fragments": tuple(
                    sorted(selected, key=lambda item: (item.span.start, item.span.end))
                )
            }
        )
    )
    verify_observation_read_window(index, result)
    return result
