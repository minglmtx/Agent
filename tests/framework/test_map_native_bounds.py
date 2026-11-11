"""Selected transport geometry: no HTTP, private reference, or task admission."""

from decimal import Decimal, localcontext
import pytest
from lab_generate_skill.sites.map.native_bounds import (
    coordinate,
    rectangle,
    area,
    request_bounds,
    serialized_xml_bounds,
    split_bounds,
    coverage_checks,
    full_original_bbox_retained,
)


def test_full_request_precision_separate_from_native_xml_and_repeat() -> None:
    values = ["-73.99999999999999", "40.700000001", "-73.9", "40.8"]
    expected = ("-73.99999999999999", "40.700000001", "-73.9", "40.8")
    assert request_bounds(values) == expected
    assert request_bounds(values) == request_bounds(expected)
    assert serialized_xml_bounds(values) == ("-74", "40.7", "-73.9", "40.8")
    assert values[0] == "-73.99999999999999"
    assert coordinate(Decimal("-0.000")) == "0"
    assert coordinate(1.5) == "1.5"
    assert coordinate(180) == "180"


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        [],
        {},
        b"1",
        "",
        "bad",
        "NaN",
        "Infinity",
        "-Infinity",
        float("nan"),
        float("inf"),
        "181",
        "-181",
        "1e-257",
        "0e9999",
        "1" * 257,
    ],
)
def test_invalid_coordinate_rejected(value: object) -> None:
    with pytest.raises(ValueError):
        coordinate(value)


@pytest.mark.parametrize(
    "values",
    [
        None,
        {},
        "0,0,1,1",
        [],
        [0, 0, 1],
        [0, 0, 1, 1, 2],
        [0, 0, 0, 1],
        [1, 0, 0, 1],
        [0, 1, 1, 0],
        [0, -91, 1, 1],
        [0, 0, 1, 91],
        [0, None, 1, 1],
        [False, 0, 1, 1],
    ],
)
def test_invalid_rectangle_rejected(values: object) -> None:
    with pytest.raises(ValueError):
        rectangle(values)


def test_area_and_split_do_not_depend_on_decimal_context() -> None:
    exact = ["0", "0", "0.5", "0.5"]
    oversized = ["0", "0", "0.500000000000000000000000000001", "0.5"]
    with localcontext() as context:
        context.prec = 5
        assert area(exact) == Decimal("0.25")
        assert request_bounds(exact) == ("0", "0", "0.5", "0.5")
        with pytest.raises(ValueError, match="area limit"):
            request_bounds(oversized)
        long = ["0", "0", "0.12345678901234567890123456789", "0.1"]
        cells = split_bounds(long)
        assert cells[0][2] == "0.061728394506172839450617283945"
        assert all(coverage_checks(long, cells).values())


@pytest.mark.parametrize("root", [[0, 0, "0.5", "0.5"], [0, 0, "0.25", 1]])
def test_split_longest_axis_exact_cover_and_recursive_union(root: list[object]) -> None:
    left, right = split_bounds(root)
    assert all(coverage_checks(root, (left, right)).values())
    assert all(
        coverage_checks(root, (*split_bounds(left), *split_bounds(right))).values()
    )
    assert full_original_bbox_retained(root, root)
    assert not full_original_bbox_retained(left, root)
    assert full_original_bbox_retained(["-0.01", "-0.01", 1, 2], root)
    assert not full_original_bbox_retained(None, root)


@pytest.mark.parametrize(
    "cells", [None, [], {}, [None], [[0, 0, 1]], [[0, 0, 1, 1]] * 256]
)
def test_malformed_empty_or_overbudget_cover_is_not_complete(cells: object) -> None:
    assert not any(coverage_checks([0, 0, "0.5", "0.5"], cells).values())


def test_partial_duplicate_overlap_and_outside_cells_never_complete() -> None:
    root = [0, 0, "0.5", "0.5"]
    left, right = split_bounds(root)
    for cells in [
        (left,),
        (left, left),
        (left, right, right),
        (["-0.1", 0, "0.25", "0.5"], right),
    ]:
        assert not coverage_checks(root, cells)["exact_original_area_covered"]
    assert not coverage_checks(root, (left, left))["interiors_disjoint"]
    assert coverage_checks(root, (left, right))["interiors_disjoint"]


def test_float_indistinguishable_split_refused() -> None:
    with pytest.raises(ValueError, match="floating bbox"):
        split_bounds(["1", "1", "1.00000000000000000001", "1.00000000000000000001"])
    with pytest.raises(ValueError):
        serialized_xml_bounds(["1", "1", "1.000000001", "1.000000001"])
