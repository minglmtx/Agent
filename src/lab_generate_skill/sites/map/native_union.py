"""Merge complete actual native children only; keep original HTTP errors apart.

This is the selected original full-bbox compatibility envelope, never an
original HTTP200 claim, browser download, independent DB reference, or verdict.
"""

import hashlib
from typing import Any
import xml.etree.ElementTree as ET
from .native_bounds import request_bounds, coverage_checks, serialized_xml_bounds
from .native_xml import (
    COORD_NAMES,
    UNION_VERSION,
    UNION_BYTES,
    UNION_OBJECTS,
    parse_native_xml,
)


def _semantic(item: ET.Element) -> tuple[Any, ...]:
    children = [(child.tag, tuple(sorted(child.attrib.items()))) for child in item]
    ordered = [v for v in children if v[0] != "tag"]
    tags = sorted(v for v in children if v[0] == "tag")
    return tuple(sorted(item.attrib.items())), tuple(ordered), tuple(tags)


def union_xml(original: object, leaves: object) -> tuple[bytes, dict[str, Any]]:
    bounds = request_bounds(original)
    if not isinstance(leaves, (list, tuple)) or not leaves or len(leaves) > 255:
        raise ValueError("Bounded nonempty actual native children required")
    if any(not isinstance(row, (list, tuple)) or len(row) != 2 for row in leaves):
        raise ValueError("Each native child requires request bounds and response bytes")
    coverage = coverage_checks(bounds, [row[0] for row in leaves])
    if not all(coverage.values()):
        raise ValueError("Native child rectangles do not exactly cover original bbox")
    objects: dict[tuple[str, str], tuple[tuple[Any, ...], ET.Element]] = {}
    root_attributes: dict[str, str] | None = None
    for cell, payload in leaves:
        parsed = parse_native_xml(payload)
        if parsed.bounds != serialized_xml_bounds(cell):
            raise ValueError("Actual native child XML bounds differ from request")
        if root_attributes is None:
            root_attributes = parsed.root_attributes
        elif parsed.root_attributes != root_attributes:
            raise ValueError("Native child XML root protocol changed")
        root = ET.fromstring(payload)
        for item in root:
            if item.tag == "bounds":
                continue
            key = (item.tag, item.attrib["id"])
            semantic = _semantic(item)
            if key in objects and objects[key][0] != semantic:
                raise ValueError(
                    "Native duplicate ID changed attributes, tags or ordered references"
                )
            if key not in objects:
                objects[key] = (semantic, item)
            if len(objects) > UNION_OBJECTS:
                raise ValueError(
                    "Complete native union exceeds object inspection budget"
                )
    attributes = dict(root_attributes or {})
    attributes["generator"] = UNION_VERSION
    merged = ET.Element("osm", attributes)
    ET.SubElement(
        merged,
        "bounds",
        dict(zip(COORD_NAMES, serialized_xml_bounds(bounds), strict=True)),
    )
    for kind in ("node", "way", "relation"):
        for key in sorted(
            (key for key in objects if key[0] == kind), key=lambda key: int(key[1])
        ):
            merged.append(objects[key][1])
    payload = ET.tostring(merged, encoding="utf-8", xml_declaration=True)
    if len(payload) > UNION_BYTES:
        raise ValueError("Complete native union exceeds byte inspection budget")
    nodes = {key[1] for key in objects if key[0] == "node"}
    if any(
        nd.attrib["ref"] not in nodes
        for key, (_, item) in objects.items()
        if key[0] == "way"
        for nd in item.findall("nd")
    ):
        raise ValueError("Complete union lost native way member nodes")
    return payload, dict(
        version=UNION_VERSION,
        counts={
            kind: sum(key[0] == kind for key in objects)
            for kind in ("node", "way", "relation")
        },
        sha256=hashlib.sha256(payload).hexdigest(),
        bytes=len(payload),
        bounds=list(bounds),
        serialized_native_xml_bounds=list(serialized_xml_bounds(bounds)),
        coverage=coverage,
        native_children=len(leaves),
        all_native_child_http200_required=True,
        native_single_request_success=False,
        native_node_limit_changed=False,
        artifact_download_completed=False,
        task_admitted=False,
    )
