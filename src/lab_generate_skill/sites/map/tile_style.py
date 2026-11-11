"""Bind generated native Mapnik SQL to the same original private tile database."""

from pathlib import Path
import os
import stat
import re
import xml.etree.ElementTree as ET
from lab_generate_skill.ports.lifecycle import OperationControl


def private_style(raw: bytes) -> bytes:
    if (
        type(raw) is not bytes
        or not raw
        or len(raw) > 16 * 1024**2
        or b"<!ENTITY" in raw.upper()
    ):
        raise ValueError("Complete generated native Mapnik XML required")
    declarations = raw.upper().count(b"<!DOCTYPE")
    if declarations and (
        declarations != 1
        or re.search(rb"<!DOCTYPE[ \t\r\n]+Map[ \t\r\n]*\[[ \t\r\n]*\][ \t\r\n]*>", raw)
        is None
    ):
        raise ValueError("Only the original Carto empty Map doctype is supported")
    tree = ET.fromstring(raw)
    if tree.tag != "Map":
        raise ValueError("Native Mapnik Map root required")
    count = 0
    for datasource in tree.findall(".//Datasource"):
        params = {
            node.attrib.get("name"): node for node in datasource.findall("Parameter")
        }
        if len(params) != len(datasource.findall("Parameter")):
            raise ValueError("Duplicate native Mapnik database parameter")
        if params.get("type") is None or params["type"].text != "postgis":
            continue
        count += 1
        for key, value in (
            ("host", "/state/run"),
            ("user", "renderer"),
            ("dbname", "gis"),
        ):
            node = params.get(key)
            if node is None:
                node = ET.SubElement(datasource, "Parameter", {"name": key})
            node.text = value
        for key in ("password", "port"):
            if key in params:
                datasource.remove(params[key])
    if count == 0:
        raise ValueError("Native tile style contains no original PostGIS datasource")
    result = ET.tostring(tree, encoding="utf-8", xml_declaration=True)
    if not isinstance(result, bytes):
        raise ValueError("Complete native XML serialization must return bytes")
    return result


def rebind_style(path: Path, control: OperationControl) -> None:
    control.checkpoint()
    if path.resolve(strict=True) != path:
        raise ValueError("Private generated style alias refused")
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != os.getuid()
        or not 0 < info.st_size <= 16 * 1024**2
    ):
        raise ValueError("Owned complete generated style required")
    raw = path.read_bytes()
    patched = private_style(raw)
    control.checkpoint()
    # This file was created by the original compile command in a fresh private
    # style directory. Partial write failures remain in the failed generation.
    with path.open("wb") as stream:
        stream.write(patched)
        stream.flush()
        os.fsync(stream.fileno())
    control.checkpoint()
