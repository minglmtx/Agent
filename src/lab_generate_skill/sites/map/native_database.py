"""Validate separately captured full native DB expansion; never derive it from XML.

Selected capsule map_native_bbox_reference.database_objects semantics. The
private 500000-object budget is distinct from the unchanged native HTTP cap.
Actual DB execution, provenance and immutable file reading remain caller duties.
"""

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Any
from .native_bounds import Bounds, request_bounds
from .native_xml import positive_id, stored_coordinate, UNION_OBJECTS

DATABASE_VERSION = "map-native-osm-expanded-database-reference-v1"


@dataclass(frozen=True)
class NativeDatabase:
    bounds: Bounds
    objects: dict[str, dict[str, dict[str, Any]]]
    initial_node_ids: tuple[str, ...]


def database_objects(value: object, original_bounds: object) -> NativeDatabase:
    bounds = request_bounds(original_bounds)
    if (
        not isinstance(value, dict)
        or set(value)
        != {"version", "bounds", "initial_node_ids", "nodes", "ways", "relations"}
        or value["version"] != DATABASE_VERSION
        or request_bounds(value["bounds"]) != bounds
    ):
        raise ValueError("Exact complete independent native DB reference required")
    objects: dict[str, dict[str, dict[str, Any]]] = {
        k: {} for k in ("node", "way", "relation")
    }
    total = 0
    for plural, kind in (("nodes", "node"), ("ways", "way"), ("relations", "relation")):
        rows = value[plural]
        if not isinstance(rows, list):
            raise ValueError("Complete native DB object lists required")
        total += len(rows)
        if total > UNION_OBJECTS:
            raise ValueError("Private full reference object budget exceeded")
        fields = {"id", "version", "tags"} | (
            {"lat", "lon"}
            if kind == "node"
            else {"nodes"} if kind == "way" else {"members"}
        )
        for row in rows:
            if not isinstance(row, dict) or set(row) != fields:
                raise ValueError("Native reference object schema differs")
            ident = positive_id(row["id"])
            if ident in objects[kind]:
                raise ValueError("Duplicate independent native ID")
            tags = row["tags"]
            if not isinstance(tags, dict) or any(
                not isinstance(k, str) or not k or not isinstance(v, str)
                for k, v in tags.items()
            ):
                raise ValueError("Malformed native DB tags")
            record: dict[str, Any] = dict(
                version=positive_id(row["version"]), tags=dict(tags)
            )
            if kind == "node":
                lat, lon = stored_coordinate(row["lat"]), stored_coordinate(row["lon"])
                if not -90 <= Decimal(lat) <= 90:
                    raise ValueError("Native node latitude invalid")
                record.update(lat=lat, lon=lon)
            elif kind == "way":
                if not isinstance(row["nodes"], list) or not row["nodes"]:
                    raise ValueError("Complete ordered native way nodes required")
                record["nodes"] = [positive_id(n) for n in row["nodes"]]
            else:
                if not isinstance(row["members"], list):
                    raise ValueError("Complete ordered relation members required")
                members = []
                for m in row["members"]:
                    if (
                        not isinstance(m, dict)
                        or set(m) != {"type", "ref", "role"}
                        or not isinstance(m["type"], str)
                        or m["type"] not in objects
                        or not isinstance(m["role"], str)
                    ):
                        raise ValueError("Malformed native DB relation member")
                    members.append(
                        dict(type=m["type"], ref=positive_id(m["ref"]), role=m["role"])
                    )
                record["members"] = members
            objects[kind][ident] = record
    initial = value["initial_node_ids"]
    if not isinstance(initial, list) or not initial:
        raise ValueError("Explicit nonempty original bbox nodes required")
    initial = [positive_id(i) for i in initial]
    if len(initial) != len(set(initial)) or any(
        i not in objects["node"] for i in initial
    ):
        raise ValueError("Initial native bbox node duplicate or missing")
    if any(
        n not in objects["node"]
        for way in objects["way"].values()
        for n in way["nodes"]
    ):
        raise ValueError("Native DB way missing exported node")
    # Node.bbox's real predicate scales Float64 bounds to native integer units.
    # Decimal-only containment incorrectly excludes some actual boundary nodes.
    west, south, east, north = [float(Decimal(v)) * 10000000 for v in bounds]
    with localcontext() as context:
        context.prec = 600
        for ident in initial:
            node = objects["node"][ident]
            x, y = int(Decimal(node["lon"]) * 10000000), int(
                Decimal(node["lat"]) * 10000000
            )
            if not (west <= x <= east and south <= y <= north):
                raise ValueError(
                    "Initial native node outside original scaled bbox predicate"
                )
    return NativeDatabase(bounds, objects, tuple(sorted(initial)))
