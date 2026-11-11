"""Measured visible AX openings plus their exact structural context.

Navigation, mandatory state and the bounded global directory remain explicit
extras. Unmeasured nodes are not declared invisible. Full source stays readable.
"""

from lab_generate_skill.domain.observation_read import (
    ObservationReadPayload,
    ObservationRegionRange,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from .observation_index import ObservationIndex
from .observation_protection import verify_observation_read_window


def public_viewport_ranges(
    index: ObservationIndex,
) -> tuple[ObservationRegionRange, ...]:
    """Only measured visible nodes actually used by the viewport selector."""
    viewport = index.viewport
    if viewport is None:
        return ()
    captured = {element.node_id: element for element in viewport.elements}
    selections = []
    for node in index.nodes:
        element = captured.get(node.node_id) if node.node_id is not None else None
        if element is None or element.visibility is None or element.visibility <= 0:
            continue
        box = element.box
        if (
            box is None
            or box.width == 0
            or box.height == 0
            or not (
                box.x < viewport.width
                and box.x + box.width > 0
                and box.y < viewport.height
                and box.y + box.height > 0
            )
        ):
            continue  # Geometry is necessary too; visibility alone grants no position.
        region = index.at(index.offsets[node.line])
        if region.kind == "table_row":
            selection = ObservationRegionRange(
                region_id=region.region_id, unit="whole_region"
            )
        else:
            region = index.regions[node.line]
            selection = ObservationRegionRange(
                region_id=region.region_id,
                unit="codepoints",
                start=0,
                end=region.opening_span.end - region.opening_span.start,
            )
        selections.append(selection)
    return tuple(selections)


def with_public_viewport(
    index: ObservationIndex, original: ObservationReadPayload
) -> ObservationReadPayload:
    verify_observation_read_window(index, original)
    if index.viewport is None:
        return original  # Structural legacy branch, never called a measured viewport.
    fragments = {fragment.span: fragment for fragment in original.fragments}
    for selection in public_viewport_ranges(index):
        for fragment in index.fragments((selection,)):
            fragments.setdefault(fragment.span, fragment)
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
