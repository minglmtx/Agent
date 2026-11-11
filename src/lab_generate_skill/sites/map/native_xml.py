"""Inspect preserved native OSM responses, without constructing a DB oracle.

Adapted from the selected capsule's map_osm_artifact.parse_xml and
map_osm_native_reference.xml_objects. Native children retain their original
32 MiB/100000-object limits; explicit adapted unions have separate budgets.
"""

from dataclasses import dataclass
from decimal import Decimal, localcontext
import hashlib
import json
import re
from typing import Any
import xml.etree.ElementTree as ET
from .native_bounds import Bounds, coordinate, rectangle

NATIVE_BYTES = 32 * 1024 * 1024
NATIVE_OBJECTS = 100000
UNION_BYTES = 128 * 1024 * 1024
UNION_OBJECTS = 500000
UNION_VERSION = "map-native-full-bbox-union-v1"
COORD_NAMES = ("minlon", "minlat", "maxlon", "maxlat")


def positive_id(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[1-9][0-9]*", value) is None:
        raise ValueError("Invalid native OSM object identifier")
    return value


def stored_coordinate(value: object) -> str:
    text = coordinate(value)
    number = Decimal(text)
    with localcontext() as context:
        context.prec = 600
        if number != number.quantize(Decimal("0.0000001")):
            raise ValueError("Coordinate exceeds native OSM precision")
    return text


@dataclass(frozen=True)
class ParsedXML:
    bounds: Bounds
    root_attributes: dict[str, str]
    objects: dict[str, dict[str, dict[str, Any]]]
    signature: str

    def semantic_objects(self) -> dict[str, dict[str, dict[str, Any]]]:
        """DB comparison includes versions/geometry/tags/ordered memberships.

        Attribute-complete signatures remain separate for native child union
        conflict detection; API bytes must never supply expected DB objects.
        """
        return {
            kind: {
                ident: {k: v for k, v in item.items() if k != "attributes"}
                for ident, item in rows.items()
            }
            for kind, rows in self.objects.items()
        }


def parse_native_xml(payload: object) -> ParsedXML:
    return _parse(payload, adapted=False)


def parse_adapted_xml(payload: object) -> ParsedXML:
    return _parse(payload, adapted=True)


def _parse(payload: object, *, adapted: bool) -> ParsedXML:
    byte_limit = UNION_BYTES if adapted else NATIVE_BYTES
    object_limit = UNION_OBJECTS if adapted else NATIVE_OBJECTS
    if not isinstance(payload, bytes) or not 1 <= len(payload) <= byte_limit:
        raise ValueError("OSM response empty or over inspection byte budget")
    # Native Rails emits UTF-8. Reject alternate encodings before the entity
    # guard; UTF-16 NULs must not bypass a byte-level DOCTYPE/ENTITY check.
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("Native OSM response requires UTF-8") from None
    if "\0" in text or "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("Native OSM response must not contain document entities")
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        raise ValueError("Malformed OSM XML response") from None
    if root.tag != "osm" or root.attrib.get("version") != "0.6":
        raise ValueError("Expected native OSM 0.6 response")
    if adapted and root.attrib.get("generator") != UNION_VERSION:
        raise ValueError("Explicit adapted union generator required")
    if len(root) > object_limit + 1:
        raise ValueError("Too many native OSM objects")
    bounds_nodes = root.findall("bounds")
    if len(bounds_nodes) != 1:
        raise ValueError("One native response bounds element required")
    bounds = rectangle(
        [stored_coordinate(bounds_nodes[0].attrib.get(n)) for n in COORD_NAMES]
    )
    objects: dict[str, dict[str, dict[str, Any]]] = {
        k: {} for k in ("node", "way", "relation")
    }
    for element in root:
        kind = element.tag
        if kind == "bounds":
            continue
        if kind not in objects:
            raise ValueError("Unexpected native OSM response element")
        ident = positive_id(element.attrib.get("id"))
        if ident in objects[kind]:
            raise ValueError("Duplicate native OSM object")
        value: dict[str, Any] = dict(
            version=positive_id(element.attrib.get("version")),
            attributes=dict(element.attrib),
            tags={},
        )
        if kind == "node":
            lat = stored_coordinate(element.attrib.get("lat"))
            lon = stored_coordinate(element.attrib.get("lon"))
            if not -90 <= Decimal(lat) <= 90:
                raise ValueError("Native node outside latitude range")
            value.update(lat=lat, lon=lon)
        elif kind == "way":
            value["nodes"] = []
        else:
            value["members"] = []
        for child in element:
            if child.tag == "tag":
                key, val = child.attrib.get("k"), child.attrib.get("v")
                if (
                    not isinstance(key, str)
                    or not key
                    or not isinstance(val, str)
                    or key in value["tags"]
                ):
                    raise ValueError("Malformed or duplicate native OSM tag")
                value["tags"][key] = val
            elif child.tag == "nd" and kind == "way":
                value["nodes"].append(positive_id(child.attrib.get("ref")))
            elif child.tag == "member" and kind == "relation":
                member_type, role = child.attrib.get("type"), child.attrib.get("role")
                if member_type not in objects or not isinstance(role, str):
                    raise ValueError("Malformed native relation member")
                value["members"].append(
                    dict(
                        type=member_type,
                        ref=positive_id(child.attrib.get("ref")),
                        role=role,
                    )
                )
            else:
                raise ValueError("Unexpected native OSM object child")
        objects[kind][ident] = value
    for way in objects["way"].values():
        if not way["nodes"] or any(n not in objects["node"] for n in way["nodes"]):
            raise ValueError("Native response way lacks referenced nodes")
    canonical = dict(bounds=bounds, root_attributes=dict(root.attrib), objects=objects)
    signature = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return ParsedXML(bounds, dict(root.attrib), objects, signature)
