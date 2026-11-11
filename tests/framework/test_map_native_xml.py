"""Native bytes stay distinct from adapted union and independent DB geometry."""

from typing import Any
import pytest
from lab_generate_skill.sites.map import native_xml, native_union
from lab_generate_skill.sites.map.native_xml import parse_native_xml, parse_adapted_xml
from lab_generate_skill.sites.map.native_union import union_xml
from map_xml_fixtures import ROOT, LEFT, RIGHT, OBJECTS, xml, leaves


def test_native_attributes_geometry_order_and_repeat() -> None:
    payload = xml()
    result = parse_native_xml(payload)
    assert result == parse_native_xml(payload)
    assert result.bounds == ROOT
    assert (
        result.objects["node"]["1"]["attributes"]["timestamp"] == "2024-01-01T00:00:00Z"
    )
    semantic = result.semantic_objects()
    assert semantic["node"]["1"] == dict(
        version="2", tags={"name": "A"}, lat="0.1", lon="0.1"
    )
    assert semantic["way"]["3"]["nodes"] == ["2", "1"]
    assert semantic["relation"]["4"]["members"][-1] == dict(
        type="relation", ref="999", role="outer"
    )
    assert "attributes" not in semantic["node"]["1"]
    assert payload == xml()


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "<osm/>",
        {},
        b"",
        b"<",
        b"<osm version='0.5'/>",
        b"<html/>",
        b"\xff",
        b"<!DOCTYPE osm [<!ENTITY e 'x'>]><osm>&e;</osm>",
        "<!DOCTYPE osm><osm/>".encode("utf-16"),
    ],
)
def test_empty_wrong_type_malformed_encoding_and_entities_rejected(
    payload: object,
) -> None:
    with pytest.raises(ValueError):
        parse_native_xml(payload)


@pytest.mark.parametrize(
    "before,after",
    [
        ('id="1"', 'id="0"'),
        ('id="1"', 'id="01"'),
        ('version="2"', 'version="0"'),
        ('lat="0.1"', 'lat="91"'),
        ('lon="0.1"', 'lon="181"'),
        ('lat="0.1"', 'lat="0.12345678"'),
        ('lat="0.1"', 'lat="NaN"'),
        ('<nd ref="2"/>', '<nd ref="999"/>'),
        ('<nd ref="2"/><nd ref="1"/>', ""),
        ('type="way"', 'type="unknown"'),
        ('role="outer"', ""),
        ('<tag k="name" v="A"/>', '<tag k="name" v="A"/><tag k="name" v="B"/>'),
        ('<tag k="name" v="A"/>', '<tag k="" v="A"/>'),
        ('<tag k="name" v="A"/>', '<nd ref="2"/>'),
        ("</osm>", '<node id="2" version="1" lat="0" lon="0"/></osm>'),
        ("</osm>", "<unknown/></osm>"),
        ('minlat="0"', 'minlat="2"'),
    ],
)
def test_illegal_native_schema_or_incomplete_way_rejected(
    before: str, after: str
) -> None:
    with pytest.raises(ValueError):
        parse_native_xml(xml().replace(before.encode(), after.encode()))


def test_explicit_empty_native_response_is_parseable_not_a_success() -> None:
    result = parse_native_xml(xml(objects=""))
    assert all(not rows for rows in result.objects.values())
    with pytest.raises(ValueError, match="bounds"):
        parse_native_xml(b'<osm version="0.6"/>')
    with pytest.raises(ValueError, match="bounds"):
        parse_native_xml(
            xml().replace(
                b"</osm>",
                b'<bounds minlon="0" minlat="0" maxlon="1" maxlat="1"/></osm>',
            )
        )


def test_byte_and_object_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = xml()
    monkeypatch.setattr(native_xml, "NATIVE_BYTES", len(payload))
    monkeypatch.setattr(native_xml, "NATIVE_OBJECTS", 4)
    assert parse_native_xml(payload).bounds == ROOT
    with pytest.raises(ValueError, match="byte budget"):
        parse_native_xml(payload + b" ")
    monkeypatch.setattr(native_xml, "NATIVE_OBJECTS", 3)
    with pytest.raises(ValueError, match="objects"):
        parse_native_xml(payload)


def test_full_native_union_deduplicates_preserves_metadata_and_roundtrips() -> None:
    children = leaves()
    payload, summary = union_xml(ROOT, children)
    assert (payload, summary) == union_xml(ROOT, children)
    result = parse_adapted_xml(payload)
    assert result.semantic_objects() == parse_native_xml(xml()).semantic_objects()
    assert (
        result.objects["node"]["1"]["attributes"]["timestamp"] == "2024-01-01T00:00:00Z"
    )
    assert summary["counts"] == {"node": 2, "way": 1, "relation": 1}
    assert summary["native_children"] == 2 and all(summary["coverage"].values())
    assert not any(
        summary[k]
        for k in (
            "native_single_request_success",
            "native_node_limit_changed",
            "artifact_download_completed",
            "task_admitted",
        )
    )
    assert children == leaves()
    with pytest.raises(ValueError, match="generator"):
        parse_adapted_xml(xml())


@pytest.mark.parametrize(
    "children",
    [
        None,
        [],
        {},
        [None],
        [(LEFT,)],
        [(LEFT, xml(LEFT))],
        [(LEFT, xml(LEFT)), (LEFT, xml(LEFT))],
        [(LEFT, b"error"), (RIGHT, xml(RIGHT))],
        [(LEFT, xml(ROOT)), (RIGHT, xml(RIGHT))],
    ],
)
def test_partial_wrong_type_missing_overlap_or_bad_child_never_unions(
    children: object,
) -> None:
    with pytest.raises(ValueError):
        union_xml(ROOT, children)


@pytest.mark.parametrize(
    "before,after",
    [
        ('version="2"', 'version="3"'),
        ('v="A"', 'v="B"'),
        ('lat="0.1"', 'lat="0.11"'),
        ('timestamp="2024-01-01T00:00:00Z"', 'timestamp="2024-02-01T00:00:00Z"'),
        ('<nd ref="2"/><nd ref="1"/>', '<nd ref="1"/><nd ref="2"/>'),
        ('role="outer"', 'role="inner"'),
    ],
)
def test_conflicting_duplicate_objects_refused(before: str, after: str) -> None:
    with pytest.raises(ValueError, match="duplicate ID"):
        union_xml(
            ROOT,
            [(LEFT, xml(LEFT)), (RIGHT, xml(RIGHT, OBJECTS.replace(before, after)))],
        )


def test_tag_order_irrelevant_but_root_protocol_and_union_budgets_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = OBJECTS.replace(
        '<tag k="name" v="A"/>', '<tag k="name" v="A"/><tag k="x" v="y"/>'
    )
    second = first.replace(
        '<tag k="name" v="A"/><tag k="x" v="y"/>',
        '<tag k="x" v="y"/><tag k="name" v="A"/>',
    )
    payload, _ = union_xml(
        ROOT, [(LEFT, xml(LEFT, first)), (RIGHT, xml(RIGHT, second))]
    )
    assert parse_adapted_xml(payload).objects["node"]["1"]["tags"] == {
        "name": "A",
        "x": "y",
    }
    with pytest.raises(ValueError, match="root protocol"):
        union_xml(ROOT, [(LEFT, xml(LEFT)), (RIGHT, xml(RIGHT, generator="changed"))])
    monkeypatch.setattr(native_union, "UNION_OBJECTS", 3)
    with pytest.raises(ValueError, match="object inspection budget"):
        union_xml(ROOT, leaves())
    monkeypatch.setattr(native_union, "UNION_OBJECTS", 4)
    monkeypatch.setattr(native_union, "UNION_BYTES", 1)
    with pytest.raises(ValueError, match="byte inspection budget"):
        union_xml(ROOT, leaves())
