"""Full original Carto output reproduction; preserve every non-connection byte meaning."""

import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.sites.map.tile_style import private_style
from map_services_fixtures import STYLE

RAW = Path(
    "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-map-intake-20261029-v1/style-reproduction-4851245/reproduced-mapnik.xml"
)
SHA = "a7398f3ca88a9c447877890e96a0eb5ff0654d59f143dfc0222a1a2d7ece31e1"


def test_full_frozen_carto_compilation_only_rebinds_native_connections() -> None:
    raw = RAW.read_bytes()
    assert len(raw) == 2824034 and hashlib.sha256(raw).hexdigest() == SHA
    assert b"<!DOCTYPE Map[]>" in raw and b"<!ENTITY" not in raw
    result = private_style(raw)
    before, after = ET.fromstring(raw), ET.fromstring(result)
    assert private_style(result) == result
    assert before.attrib == after.attrib
    left, right = before.findall(".//Datasource"), after.findall(".//Datasource")
    assert len(left) == len(right) and left
    count = 0
    for original, actual in zip(left, right, strict=True):
        params = {p.attrib["name"]: p.text for p in original.findall("Parameter")}
        if params.get("type") != "postgis":
            assert ET.tostring(original) == ET.tostring(actual)
            continue
        count += 1
        changed = {p.attrib["name"]: p.text for p in actual.findall("Parameter")}
        assert {k: changed[k] for k in ("host", "user", "dbname")} == dict(
            host="/state/run", user="renderer", dbname="gis"
        )
        assert "password" not in changed and "port" not in changed
        assert {
            k: v
            for k, v in params.items()
            if k not in ("host", "user", "dbname", "password", "port")
        } == {
            k: v
            for k, v in changed.items()
            if k not in ("host", "user", "dbname", "password", "port")
        }
        for tree in (original, actual):
            for node in list(tree):
                if node.tag == "Parameter" and node.attrib.get("name") in (
                    "host",
                    "user",
                    "dbname",
                    "password",
                    "port",
                ):
                    tree.remove(node)
    assert count > 0
    assert ET.tostring(before) == ET.tostring(after)


@pytest.mark.parametrize(
    "declaration",
    [b"<!DOCTYPE Map[]>", b"<!DOCTYPE Map [ ]>", b"<!DOCTYPE Map [\n\t]>"],
)
def test_empty_native_doctype_and_repeat(declaration: bytes) -> None:
    assert private_style(declaration + STYLE) == private_style(STYLE)


@pytest.mark.parametrize(
    "declaration",
    [
        b'<!DOCTYPE Map SYSTEM "file:///etc/passwd">',
        b'<!DOCTYPE Map PUBLIC "x" "https://invalid.example/">',
        b'<!DOCTYPE Map [<!ENTITY x "value">]>',
        b"<!DOCTYPE Map [<!ELEMENT Map ANY>]>",
        b"<!DOCTYPE Other[]>",
        b"<!DOCTYPE Map><Map/>",
        b"<!DOCTYPE Map[]><!DOCTYPE Map[]>",
        b"<!doctype Map[]>",
        b"<!DOCTYPE Map[]",
    ],
)
def test_nonempty_external_wrong_or_duplicate_doctype_refused(
    declaration: bytes,
) -> None:
    with pytest.raises((ValueError, ET.ParseError)):
        private_style(declaration + STYLE)


@pytest.mark.parametrize(
    "raw",
    [None, "", 1, [], b"", b" " * (16 * 1024**2 + 1)],
    ids=["none", "text", "int", "list", "empty", "oversize"],
)
def test_invalid_or_extreme_complete_style_input(raw: Any) -> None:
    with pytest.raises(ValueError):
        private_style(raw)
