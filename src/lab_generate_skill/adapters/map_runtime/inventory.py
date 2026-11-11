"""Consume the original complete-copy inventory; legacy paths are audit labels only."""

from pathlib import PurePosixPath
from typing import Any
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.map_runtime_inputs import MapRuntimeTree
from lab_generate_skill.domain.map_runtime_inventory import (
    MapRuntimeInventory,
    MapRuntimeMember,
)


def parse_inventory(
    raw: dict[str, Any], declaration: MapRuntimeTree
) -> MapRuntimeInventory:
    if set(raw) != {
        "source",
        "destination",
        "files",
        "directories",
        "excluded",
        "bytes",
    }:
        raise ValueError("Original complete-copy inventory fields differ")
    if raw["destination"] != declaration.source_root or type(raw["source"]) is not str:
        raise ValueError("Original published runtime root differs")
    original_root = PurePosixPath(SiteFilesPlan.canonical(raw["source"]))
    if (
        type(raw["files"]) is not list
        or not 1 <= len(raw["files"]) <= 100000
        or type(raw["directories"]) is not list
        or type(raw["excluded"]) is not list
    ):
        raise ValueError("Explicit complete runtime inventory lists required")
    members = []
    for row in raw["files"]:
        if type(row) is not dict or set(row) != {
            "relative",
            "source",
            "resolved_source",
            "state",
            "sha256",
            "bytes",
        }:
            raise ValueError("Original runtime inventory member fields differ")
        state = row["state"]
        if (
            type(state) is not list
            or len(state) != 6
            or any(type(x) is not int or x < 0 for x in state)
        ):
            raise ValueError("Original source file stat declaration differs")
        if type(row["relative"]) is not str or row["bytes"] != state[2]:
            raise ValueError("Original source member path/size differs")
        # Never open these historical labels. Staging uses only the bound
        # published workspace root plus the validated relative member path.
        expected_label = str(original_root / row["relative"])
        if row["source"] != expected_label or row["resolved_source"] != expected_label:
            raise ValueError("Original inventory records an unexpected source alias")
        members.append(
            MapRuntimeMember(
                file=ReleaseFile(
                    path=row["relative"],
                    sha256=row["sha256"],
                    size_bytes=row["bytes"],
                    executable=bool(state[5] & 0o111),
                ),
                mode=state[5],
            )
        )
    return MapRuntimeInventory(
        role=declaration.role,
        files=tuple(members),
        directories=tuple(raw["directories"]),
        excluded=tuple(raw["excluded"]),
        size_bytes=raw["bytes"],
    )
