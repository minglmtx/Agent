"""Exact request rectangles shared by MapData transport and independent review.

Selected capsule map_native_request_bounds/map_native_bbox_batch semantics:
request decimals are not stored-node coordinates. Only XML serialization uses
the native Float64 %.7f rule. This pure module performs no request or admission.
"""

from decimal import Decimal, InvalidOperation, localcontext
from typing import TypeAlias

Bounds: TypeAlias = tuple[str, str, str, str]
MAX_CELLS = 255


def coordinate(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("Malformed native request bound")
    text = str(value)
    if len(text) > 256:
        raise ValueError("Native bound exceeds numeric inspection budget")
    try:
        number = Decimal(text)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Malformed native request bound") from None
    if not number.is_finite() or not -180 <= number <= 180:
        raise ValueError("Native bound outside finite geographic range")
    if abs(int(number.as_tuple().exponent)) > 256:
        raise ValueError("Native bound exceeds numeric inspection budget")
    formatted = format(number, "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted if number else "0"


def rectangle(values: object) -> Bounds:
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        raise ValueError("Four native request bounds required")
    west, south, east, north = (coordinate(v) for v in values)
    if not (
        Decimal(west) < Decimal(east) and -90 <= Decimal(south) < Decimal(north) <= 90
    ):
        raise ValueError("Invalid native request rectangle")
    return west, south, east, north


def area(values: object) -> Decimal:
    west, south, east, north = map(Decimal, rectangle(values))
    # Inputs allow 256 decimal places; ambient Decimal precision must not turn
    # a slightly oversized request into the original native 0.25 area bound.
    with localcontext() as context:
        context.prec = 600
        return (east - west) * (north - south)


def request_bounds(values: object) -> Bounds:
    result = rectangle(values)
    if area(result) > Decimal("0.25"):
        raise ValueError("Original bbox exceeds unchanged native map area limit")
    return result


def serialized_xml_bounds(values: object) -> Bounds:
    return rectangle([format(float(Decimal(v)), ".7f") for v in rectangle(values)])


def split_bounds(values: object) -> tuple[Bounds, Bounds]:
    west, south, east, north = map(Decimal, request_bounds(values))
    with localcontext() as context:
        context.prec = 600
        if east - west >= north - south:
            middle = (west + east) / 2
            cells = ((west, south, middle, north), (middle, south, east, north))
        else:
            middle = (south + north) / 2
            cells = ((west, south, east, middle), (west, middle, east, north))
    left, right = (request_bounds([format(v, "f") for v in c]) for c in cells)
    for cell in (left, right):
        if float(cell[2]) <= float(cell[0]) or float(cell[3]) <= float(cell[1]):
            raise ValueError("Native floating bbox cannot be subdivided further")
    return left, right


def coverage_checks(original: object, cells: object) -> dict[str, bool]:
    root = tuple(map(Decimal, request_bounds(original)))
    failed = dict(
        all_cells_within_original=False,
        interiors_disjoint=False,
        exact_original_area_covered=False,
    )
    if not isinstance(cells, (list, tuple)) or not 1 <= len(cells) <= MAX_CELLS:
        return failed
    try:
        boxes = [tuple(map(Decimal, request_bounds(c))) for c in cells]
    except ValueError:
        return failed
    inside = all(
        root[0] <= b[0] < b[2] <= root[2] and root[1] <= b[1] < b[3] <= root[3]
        for b in boxes
    )
    disjoint = all(
        min(a[2], b[2]) <= max(a[0], b[0]) or min(a[3], b[3]) <= max(a[1], b[1])
        for i, a in enumerate(boxes)
        for b in boxes[i + 1 :]
    )
    with localcontext() as context:
        context.prec = 600
        actual = sum(((b[2] - b[0]) * (b[3] - b[1]) for b in boxes), Decimal(0))
        expected = (root[2] - root[0]) * (root[3] - root[1])
    return dict(
        all_cells_within_original=inside,
        interiors_disjoint=disjoint,
        exact_original_area_covered=inside and disjoint and actual == expected,
    )


def full_original_bbox_retained(current: object, original: object) -> bool:
    """Closing the sidebar may enlarge the view; narrowing never bypasses cap."""
    try:
        west, south, east, north = map(Decimal, rectangle(current))
        left, bottom, right, top = map(Decimal, rectangle(original))
    except ValueError:
        return False
    return west <= left and south <= bottom and east >= right and north >= top
