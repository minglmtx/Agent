"""Separate synthetic DB fixture + actual XML union; never a response-derived oracle."""

from copy import deepcopy
from typing import Any
import pytest
from lab_generate_skill.sites.map.native_database import (
    database_objects,
    DATABASE_VERSION,
)
from lab_generate_skill.sites.map.native_compare import compare_database
from lab_generate_skill.sites.map.native_union import union_xml
from map_xml_fixtures import ROOT, LEFT, RIGHT, xml, leaves


def database() -> dict[str, Any]:
    return dict(
        version=DATABASE_VERSION,
        bounds=list(ROOT),
        initial_node_ids=["1", "2"],
        nodes=[
            dict(id="1", version="2", lat="0.1", lon="0.1", tags={"name": "A"}),
            dict(id="2", version="1", lat="0.2", lon="0.3", tags={}),
        ],
        ways=[dict(id="3", version="4", nodes=["2", "1"], tags={"highway": "road"})],
        relations=[
            dict(
                id="4",
                version="1",
                members=[
                    dict(type="way", ref="3", role=""),
                    dict(type="relation", ref="999", role="outer"),
                ],
                tags={},
            )
        ],
    )


@pytest.mark.parametrize("kind", ["native_200", "adapted_union"])
def test_full_independent_reference_compares_versions_geometry_tags_and_order(
    kind: Any,
) -> None:
    db = database()
    before = deepcopy(db)
    payload = xml() if kind == "native_200" else union_xml(ROOT, leaves())[0]
    result = compare_database(payload, ROOT, db, response_kind=kind)
    assert result["passed"] and all(result["checks"].values())
    assert result["counts"] == dict(node=2, way=1, relation=1)
    assert (
        not result["api_payload_constructed_expected_reference"]
        and not result["provenance_verified"]
    )
    assert (
        not result["native_single_map_http200_claim"]
        and not result["native_api_cap_changed"]
    )
    assert (
        compare_database(payload, ROOT, db, response_kind=kind) == result
        and db == before
    )
    normalized = database_objects(db, ROOT)
    db["ways"][0]["nodes"].reverse()
    assert normalized.objects["way"]["3"]["nodes"] == ["2", "1"]


@pytest.mark.parametrize(
    "fault",
    [
        "version",
        "geometry",
        "tags",
        "way_order",
        "member_order",
        "member_role",
        "missing_object",
        "extra_object",
    ],
)
def test_structurally_valid_difference_is_explicit_false_not_silently_ignored(
    fault: str,
) -> None:
    db = database()
    if fault == "version":
        db["nodes"][0]["version"] = "9"
    elif fault == "geometry":
        db["nodes"][0]["lat"] = "0.11"
    elif fault == "tags":
        db["nodes"][0]["tags"]["name"] = "Changed"
    elif fault == "way_order":
        db["ways"][0]["nodes"].reverse()
    elif fault == "member_order":
        db["relations"][0]["members"].reverse()
    elif fault == "member_role":
        db["relations"][0]["members"][0]["role"] = "outer"
    elif fault == "missing_object":
        db["relations"] = []
    else:
        db["relations"].append(dict(id="5", version="1", members=[], tags={}))
    result = compare_database(
        union_xml(ROOT, leaves())[0], ROOT, db, response_kind="adapted_union"
    )
    assert not result["passed"] and not all(result["checks"].values())
    assert any(any(v.values()) for v in result["mismatches"].values())


@pytest.mark.parametrize("bad", [None, {}, [], True, "", 42])
def test_absent_wrong_type_reference_rejected(bad: object) -> None:
    with pytest.raises(ValueError):
        database_objects(bad, ROOT)


@pytest.mark.parametrize(
    "fault",
    [
        "schema",
        "version",
        "bounds",
        "empty",
        "initial-empty",
        "initial-wrong-type",
        "initial-duplicate",
        "initial-missing",
        "initial-outside",
        "node-id",
        "node-version",
        "node-precision",
        "node-latitude",
        "node-tags",
        "node-extra",
        "duplicate",
        "way-missing",
        "way-empty",
        "way-type",
        "member-type",
        "member-empty",
        "member-schema",
        "member-role",
        "node-list",
    ],
)
def test_incomplete_or_illegal_native_database_remains_unusable(fault: str) -> None:
    db = database()
    if fault == "schema":
        db["extra"] = True
    elif fault == "version":
        db["version"] = "old"
    elif fault == "bounds":
        db["bounds"] = list(LEFT)
    elif fault == "empty":
        db.update(nodes=[], ways=[], relations=[])
    elif fault == "initial-empty":
        db["initial_node_ids"] = []
    elif fault == "initial-wrong-type":
        db["initial_node_ids"] = [{}]
    elif fault == "initial-duplicate":
        db["initial_node_ids"] = ["1", "1"]
    elif fault == "initial-missing":
        db["initial_node_ids"] = ["999"]
    elif fault == "initial-outside":
        db["nodes"][0]["lon"] = "0.6"
    elif fault == "node-id":
        db["nodes"][0]["id"] = True
    elif fault == "node-version":
        db["nodes"][0]["version"] = "0"
    elif fault == "node-precision":
        db["nodes"][0]["lat"] = "0.00000001"
    elif fault == "node-latitude":
        db["nodes"][0]["lat"] = "91"
    elif fault == "node-tags":
        db["nodes"][0]["tags"] = {"name": False}
    elif fault == "node-extra":
        db["nodes"][0]["account"] = "private"
    elif fault == "duplicate":
        db["nodes"].append(deepcopy(db["nodes"][0]))
    elif fault == "way-missing":
        db["ways"][0]["nodes"] = ["999"]
    elif fault == "way-empty":
        db["ways"][0]["nodes"] = []
    elif fault == "way-type":
        db["ways"][0]["nodes"] = "1"
    elif fault == "member-type":
        db["relations"][0]["members"][0]["type"] = []
    elif fault == "member-empty":
        db["relations"][0]["members"] = None
    elif fault == "member-schema":
        db["relations"][0]["members"][0]["extra"] = 1
    elif fault == "member-role":
        db["relations"][0]["members"][0]["role"] = None
    else:
        db["nodes"] = {}
    with pytest.raises(ValueError):
        database_objects(db, ROOT)


def test_expansion_nodes_outside_bbox_and_external_relation_are_retained() -> None:
    db = database()
    db["initial_node_ids"] = ["1"]
    db["nodes"][1]["lon"] = "0.6"
    result = database_objects(db, ROOT)
    assert (
        result.objects["node"]["2"]["lon"] == "0.6"
        and result.objects["relation"]["4"]["members"][1]["ref"] == "999"
    )


def test_original_float64_scaled_predicate_is_not_decimal_only_containment() -> None:
    db = database()
    bounds = ("0.1000000000000000000001", "0", "0.5", "0.5")
    db["bounds"] = list(bounds)
    assert database_objects(db, bounds).initial_node_ids == ("1", "2")


def test_private_reference_budget_exhaustion_and_invalid_expected_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import lab_generate_skill.sites.map.native_database as module

    monkeypatch.setattr(module, "UNION_OBJECTS", 3)
    with pytest.raises(ValueError, match="budget"):
        database_objects(database(), ROOT)
    with pytest.raises(ValueError):
        compare_database(xml(), ROOT, None, response_kind="native_200")


def test_smaller_serialized_region_and_empty_response_cannot_pass() -> None:
    changed = compare_database(xml(LEFT), ROOT, database(), response_kind="native_200")
    assert not changed["passed"] and not changed["original_full_bbox_preserved"]
    empty = compare_database(
        xml(objects=""), ROOT, database(), response_kind="native_200"
    )
    assert not empty["passed"] and empty["mismatches"]["node"]["missing_ids"] == [
        "1",
        "2",
    ]


@pytest.mark.parametrize("kind", [None, False, "", [], {}, "inferred"])
def test_response_kind_not_inferred(kind: Any) -> None:
    with pytest.raises(ValueError):
        compare_database(xml(), ROOT, database(), response_kind=kind)


@pytest.mark.parametrize("kind", ["native_200", "adapted_union"])
@pytest.mark.parametrize(
    "fault", ["none", "version", "way_order", "member_role", "missing_relation"]
)
def test_same_capsule_original_complete_comparison_acceptance(
    kind: Any, fault: str
) -> None:
    from map_database_original_oracle import oracle

    original = oracle()
    db = database()
    if fault == "version":
        db["nodes"][0]["version"] = "17"
    elif fault == "way_order":
        db["ways"][0]["nodes"].reverse()
    elif fault == "member_role":
        db["relations"][0]["members"][0]["role"] = "backward"
    elif fault == "missing_relation":
        db["relations"] = []
    normalized = database_objects(db, ROOT)
    old_objects, old_initial = original["database_objects"](db, ROOT)
    assert (
        normalized.objects == old_objects
        and list(normalized.initial_node_ids) == old_initial
    )
    payload = xml() if kind == "native_200" else union_xml(ROOT, leaves())[0]
    old = original[
        (
            "compare_database_native_200"
            if kind == "native_200"
            else "compare_database_union"
        )
    ](payload, ROOT, db)
    new = compare_database(payload, ROOT, db, response_kind=kind)
    assert new["passed"] == old["passed"] and new["checks"] == old["checks"]
