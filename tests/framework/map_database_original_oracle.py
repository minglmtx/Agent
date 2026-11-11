"""Exact selected capsule pure DB/XML rules only; never import its old runtime."""

import ast
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any
import xml.etree.ElementTree as ET

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
CAPSULE = W / "experiments/sft-shared-request-repair-v2/groups/38/runtime/capsule.json"
ROOT = W / "experiments/framework-map-intake-20261029-v1/original-capsule"


def oracle() -> dict[str, Any]:
    raw = CAPSULE.read_bytes()
    if (
        hashlib.sha256(raw).hexdigest()
        != "3c537fffffcf2768fc3bcedb4e567ed39565f76faf01f3b1f685614d35e724f5"
    ):
        raise ValueError("Exact original Map capsule required")
    pins = json.loads(raw)["members"]

    def add(name: str, names: set[str], namespace: dict[str, Any]) -> None:
        rel = "src/lab_generate_skill/" + name + ".py"
        source = (ROOT / rel).read_bytes()
        if hashlib.sha256(source).hexdigest() != pins[rel]["sha256"]:
            raise ValueError("Original selected oracle source changed")
        nodes = [
            n
            for n in ast.parse(source).body
            if isinstance(n, ast.FunctionDef) and n.name in names
        ]
        if {n.name for n in nodes} != names:
            raise ValueError("Original pure oracle function set differs")
        exec(
            compile(
                ast.Module(body=list[ast.stmt](nodes), type_ignores=[]),
                str(ROOT / rel),
                "exec",
            ),
            namespace,
        )

    basic: dict[str, Any] = dict(
        Decimal=Decimal,
        InvalidOperation=InvalidOperation,
        re=re,
        hashlib=hashlib,
        json=json,
        ET=ET,
        MAX_BYTES=32 * 1024 * 1024,
        MAX_OBJECTS=100000,
        COORD_NAMES=("minlon", "minlat", "maxlon", "maxlat"),
    )
    add("map_osm_artifact", {"coordinate", "positive_id", "bbox", "parse_xml"}, basic)
    request = dict(basic)
    add(
        "map_native_request_bounds",
        {"bounds_coordinate", "bbox", "native_xml_bbox", "bbox_area"},
        request,
    )
    native: dict[str, Any] = dict(
        artifact=SimpleNamespace(**basic),
        Decimal=Decimal,
        ET=ET,
        VERSION="map-native-osm-expanded-database-reference-v1",
    )
    add("map_osm_native_reference", {"_tags", "xml_objects"}, native)
    batch: dict[str, Any] = dict(artifact=SimpleNamespace(**request), Decimal=Decimal)
    add("map_native_bbox_batch", {"exact_bounds"}, batch)
    reference: dict[str, Any] = dict(
        artifact=SimpleNamespace(**request),
        native=SimpleNamespace(**native),
        exact_bounds=batch["exact_bounds"],
        Decimal=Decimal,
        ET=ET,
        hashlib=hashlib,
        MAX_UNION_OBJECTS=500000,
        MAX_UNION_BYTES=128 * 1024 * 1024,
        VERSION="map-native-full-bbox-union-v1",
    )
    add(
        "map_native_bbox_reference",
        {
            "_tags",
            "database_objects",
            "envelope_objects",
            "compare_database_union",
            "compare_database_native_200",
        },
        reference,
    )
    return reference
