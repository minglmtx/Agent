"""Complete declared files, modes and empty directories for Map input staging."""

from pathlib import PurePosixPath
from typing import Self
from pydantic import Field, field_validator, model_validator
from .validation import Contract
from .release import ReleaseFile
from .map_runtime_inputs import MapTreeRole


def relative_member(value: str) -> str:
    ReleaseFile.relative_file(value)
    if any(ord(c) < 32 for c in value):
        raise ValueError("Runtime member must not contain control characters")
    return value


class MapRuntimeMember(Contract):
    file: ReleaseFile
    mode: int = Field(ge=0, le=0o777)

    @model_validator(mode="after")
    def file_mode(self) -> Self:
        relative_member(self.file.path)
        if self.file.executable != bool(self.mode & 0o111) or not self.mode & 0o400:
            raise ValueError(
                "Original readable runtime file mode differs from content pin"
            )
        return self


class MapRuntimeInventory(Contract):
    role: MapTreeRole
    files: tuple[MapRuntimeMember, ...] = Field(min_length=1, max_length=100000)
    directories: tuple[str, ...] = Field(max_length=100000)
    excluded: tuple[str, ...] = Field(max_length=100000)
    size_bytes: int = Field(ge=1, le=2 * 1024**4)

    @field_validator("directories", "excluded")
    @classmethod
    def relative_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            relative_member(value)
        if len(set(values)) != len(values):
            raise ValueError("Repeated Map directory/exclusion declaration")
        return values

    @model_validator(mode="after")
    def complete_tree(self) -> Self:
        files = {x.file.path for x in self.files}
        directories = set(self.directories)
        if len(files) != len(self.files) or files & directories:
            raise ValueError("Map files and directories must be unique and disjoint")
        if sum(x.file.size_bytes for x in self.files) != self.size_bytes:
            raise ValueError("Complete Map inventory byte total differs")
        for name in files | directories:
            parents = {str(p) for p in PurePosixPath(name).parents if str(p) != "."}
            if not parents <= directories:
                raise ValueError("Every original parent directory must be declared")
        for name in self.excluded:
            if self.role != "frontend" or PurePosixPath(name).name not in {
                ".git",
                "log",
                "tmp",
                "storage",
                "node_modules",
            }:
                raise ValueError(
                    "Only original frontend transient exclusions are allowed"
                )
            if any(
                p == name or PurePosixPath(p).is_relative_to(name)
                for p in files | directories
            ):
                raise ValueError(
                    "Excluded input overlaps the declared runtime inventory"
                )
        required = {
            "app": {
                "baseline.json",
                "postgres/PG_VERSION",
                "postgres/global/pg_control",
            },
            "search": {
                "stage.json",
                "postgres/PG_VERSION",
                "postgres/global/pg_control",
            },
            "routing": {
                "stage.json",
                "files.jsonl",
                *(
                    p + "/us-northeast-latest.osrm." + suffix
                    for p in ("car", "bike", "foot")
                    for suffix in (
                        "mldgr",
                        "ramIndex",
                        "names",
                        "ebg_nodes",
                        "timestamp",
                        "geometry",
                        "cell_metrics",
                        "properties",
                        "edges",
                        "icd",
                        "enw",
                        "tls",
                        "partition",
                        "turn_weight_penalties",
                        "cnbg_to_ebg",
                        "datasource_names",
                        "cnbg",
                        "nbg_nodes",
                        "turn_duration_penalties",
                        "tld",
                        "maneuver_overrides",
                        "ebg",
                        "cells",
                        "fileIndex",
                        "turn_penalties_index",
                        "restrictions",
                    )
                ),
            },
            "tiles": {
                "stage.json",
                "postgres/PG_VERSION",
                "postgres/global/pg_control",
            },
            "frontend": {
                "Gemfile.lock",
                "app/assets/javascripts/index.js",
                "app/assets/javascripts/leaflet.share.js",
                "app/assets/javascripts/leaflet.layers.js",
                "vendor/assets/leaflet/leaflet.osm.js",
            },
        }[self.role]
        if not required <= files:
            raise ValueError(
                "Selected runtime inventory lacks original consumed leaves"
            )
        return self
