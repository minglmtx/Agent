"""Closed selected frontend preparation intent and result, not site admission."""

import hashlib
from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import Field, model_validator
from .validation import Contract, Sha256
from .release import ReleaseFile
from .map_services import MapServiceSpec

FRONTEND_FILES = frozenset(
    {
        "app/assets/javascripts/index.js",
        "app/assets/javascripts/leaflet.share.js",
        "app/assets/javascripts/leaflet.layers.js",
        "vendor/assets/leaflet/leaflet.osm.js",
        "app/assets/javascripts/index/browse.js",
        "app/assets/javascripts/index/notes.js",
        "app/controllers/api/map_controller.rb",
        "app/views/api/map/index.xml.builder",
        "lib/bounding_box.rb",
        "lib/osm.rb",
        "app/models/concerns/geo_record.rb",
        "config/settings.yml",
        "app/assets/javascripts/leaflet.map.js",
        "app/assets/javascripts/index/directions/fossgis_osrm.js",
    }
)
PATCH_FILES = frozenset(
    {
        "app/assets/javascripts/index.js",
        "app/assets/javascripts/leaflet.share.js",
        "app/assets/javascripts/leaflet.layers.js",
        "vendor/assets/leaflet/leaflet.osm.js",
        "app/controllers/api/map_controller.rb",
        "app/assets/javascripts/leaflet.map.js",
        "app/assets/javascripts/index/directions/fossgis_osrm.js",
    }
)


class MapFrontendChange(Contract):
    original: ReleaseFile
    content: bytes = Field(min_length=1, max_length=1024 * 1024)

    @model_validator(mode="after")
    def changed(self) -> Self:
        if (
            self.original.path not in PATCH_FILES
            or self.original.executable
            or hashlib.sha256(self.content).hexdigest() == self.original.sha256
        ):
            raise ValueError(
                "Exactly a selected nonempty changed frontend source required"
            )
        self.content.decode("utf-8")
        if b"\0" in self.content:
            raise ValueError("Frontend source cannot contain NUL bytes")
        return self

    def after(self) -> ReleaseFile:
        return ReleaseFile(
            path=self.original.path,
            sha256=hashlib.sha256(self.content).hexdigest(),
            size_bytes=len(self.content),
            executable=False,
        )


class MapFrontendPlan(Contract):
    schema_version: Literal["map-frontend-preparation/1"] = "map-frontend-preparation/1"
    spec: MapServiceSpec
    original: tuple[ReleaseFile, ...] = Field(min_length=14, max_length=14)
    changes: tuple[MapFrontendChange, ...] = Field(min_length=7, max_length=7)

    @model_validator(mode="after")
    def selected(self) -> Self:
        pins = {p.path: p for p in self.original}
        if (
            set(pins) != FRONTEND_FILES
            or {p.original.path for p in self.changes} != PATCH_FILES
        ):
            raise ValueError("Complete selected frontend read/change sets required")
        if any(
            p.executable or not 0 < p.size_bytes <= 1024 * 1024 for p in self.original
        ):
            raise ValueError("Bounded original nonexecutable frontend files required")
        if any(p.original != pins[p.original.path] for p in self.changes):
            raise ValueError("Frontend change must refer to its exact original pin")
        return self

    @property
    def marker(self) -> str:
        return str(
            PurePosixPath(self.spec.inputs.files.node_root) / "frontend-preparation"
        )

    def sha256(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class MapFrontendPrepared(Contract):
    schema_version: Literal["map-frontend-prepared/1"] = "map-frontend-prepared/1"
    preparation_sha256: Sha256
    original: tuple[ReleaseFile, ...] = Field(min_length=14, max_length=14)
    changed: tuple[ReleaseFile, ...] = Field(min_length=7, max_length=7)

    @model_validator(mode="after")
    def selected(self) -> Self:
        if {p.path for p in self.original} != FRONTEND_FILES or {
            p.path for p in self.changed
        } != PATCH_FILES:
            raise ValueError("Complete original and changed frontend receipts required")
        return self

    def check(self, plan: MapFrontendPlan) -> None:
        if (
            self.preparation_sha256 != plan.sha256()
            or self.original != plan.original
            or self.changed != tuple(c.after() for c in plan.changes)
        ):
            raise ValueError("Frontend preparation result changed original plan")
