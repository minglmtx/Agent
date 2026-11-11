"""Selected native Map runtime input identities; validation grants no execution.

Publication metadata and immutable input bytes must still be verified by the
original acquired worker before node staging. No discovery or legacy fallback.
"""

from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import (
    Field,
    field_validator,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from .validation import Contract
from .release import ReleaseFile
from .site_files import SiteFilesPlan
from .map_readonly_inputs import MapReadonlyInputs

MapImageRole = Literal["db", "web", "nominatim", "osrm", "tiles"]
MapTreeRole = Literal["app", "search", "routing", "tiles", "frontend"]
IMAGE_PINS = {
    "db": (
        "b8130ea924b49617a2ece280c236f01a53a76bdac40ca489af9cc5fdc47c5379",
        102170624,
    ),
    "web": (
        "eb420ce4367ea31001e9c6e40aeec091a0df013fddb27d6694080d4f6aafebdf",
        618127360,
    ),
    "nominatim": (
        "c4b1af09fd51d218d972e7225a39a5be04b69b3591a66a819292a67f0e9a36cd",
        398823424,
    ),
    "osrm": (
        "636a1bad2e0ce6e749fcf3976ed5e3ff918af9bf205beddfac7c1a307f8cd26c",
        49725440,
    ),
    "tiles": (
        "6e0113d4bfd51b918ee0a779ec847ee7a91a74999f2611fcbb828936e466c0b4",
        560082944,
    ),
}
TREE_ROLES = frozenset({"app", "search", "routing", "tiles", "frontend"})
MAX_METADATA_BYTES = 16 * 1024 * 1024


class MapRuntimeImage(Contract):
    role: MapImageRole
    source_path: str
    file: ReleaseFile

    @field_validator("source_path")
    @classmethod
    def canonical(cls, value: str) -> str:
        return SiteFilesPlan.canonical(value)

    @model_validator(mode="after")
    def original(self) -> Self:
        sha, size = IMAGE_PINS[self.role]
        if (
            self.file.path,
            self.file.sha256,
            self.file.size_bytes,
            self.file.executable,
        ) != (self.role + ".sif", sha, size, False) or PurePosixPath(
            self.source_path
        ).name != self.file.path:
            raise ValueError("Exact selected native Map image pin required")
        return self


class MapRuntimeTree(Contract):
    role: MapTreeRole
    source_root: str
    inventory_path: str
    inventory: ReleaseFile

    @field_validator("source_root", "inventory_path")
    @classmethod
    def canonical(cls, value: str) -> str:
        return SiteFilesPlan.canonical(value)

    @model_validator(mode="after")
    def declaration(self) -> Self:
        if (
            PurePosixPath(self.inventory_path).name != self.inventory.path
            or self.inventory.executable
            or not 0 < self.inventory.size_bytes <= MAX_METADATA_BYTES
        ):
            raise ValueError("Exact bounded nonexecutable Map inventory pin required")
        return self


class MapRuntimeInputs(Contract):
    schema_version: Literal[
        "map-native-runtime-inputs/1", "map-native-runtime-inputs/2"
    ] = "map-native-runtime-inputs/1"
    selected_source: Literal["b9101b71aacd51b61f6e"] = "b9101b71aacd51b61f6e"
    files: SiteFilesPlan
    images: tuple[MapRuntimeImage, ...] = Field(min_length=5, max_length=5)
    trees: tuple[MapRuntimeTree, ...] = Field(min_length=5, max_length=5)
    publication_path: str
    publication: ReleaseFile
    publication_job_id: str = Field(pattern=r"^[1-9][0-9]{0,19}$")
    readonly_inputs: MapReadonlyInputs | None = None

    @model_serializer(mode="wrap")
    def wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        value: dict[str, object] = handler(self)
        if self.schema_version == "map-native-runtime-inputs/1":
            value.pop("readonly_inputs", None)
        return value

    @field_validator("publication_path")
    @classmethod
    def canonical(cls, value: str) -> str:
        return SiteFilesPlan.canonical(value)

    @model_validator(mode="after")
    def selected_inputs(self) -> Self:
        retained = self.readonly_inputs
        if (self.schema_version == "map-native-runtime-inputs/2") != (
            retained is not None
        ):
            raise ValueError("Version2 requires explicit original readonly inputs")
        if retained is not None:
            source, target = map(
                PurePosixPath, (retained.source_node_root, self.files.node_root)
            )
            if (
                source.is_relative_to(target)
                or target.is_relative_to(source)
                or retained.source_instance_id == self.files.instance_id
            ):
                raise ValueError(
                    "Original readonly root must be separate from this instance"
                )
        if {x.role for x in self.images} != set(IMAGE_PINS) or {
            x.role for x in self.trees
        } != TREE_ROLES:
            raise ValueError(
                "Exactly five original images and five distinct runtime trees required"
            )
        web = next(x for x in self.images if x.role == "web")
        if web.source_path != self.files.source_path or web.file != self.files.image:
            raise ValueError("Common site files must bind the same original web image")
        if (
            PurePosixPath(self.publication_path).name != self.publication.path
            or self.publication.executable
            or not 0 < self.publication.size_bytes <= MAX_METADATA_BYTES
        ):
            raise ValueError("Exact bounded original publication receipt required")
        workspace = PurePosixPath(self.files.workspace_root)
        sources = [PurePosixPath(x.source_root) for x in self.trees]
        metadata = [
            PurePosixPath(self.publication_path),
            *(PurePosixPath(x.inventory_path) for x in self.trees),
        ]
        images = [PurePosixPath(x.source_path) for x in self.images]
        paths = sources + metadata + images
        if len(set(paths)) != len(paths) or any(
            p == workspace or not p.is_relative_to(workspace) for p in paths
        ):
            raise ValueError(
                "All distinct runtime inputs must remain inside the fixed workspace"
            )
        for source in sources:
            if any(
                p != source and (p.is_relative_to(source) or source.is_relative_to(p))
                for p in paths
            ):
                raise ValueError(
                    "Map runtime trees, images and evidence paths must not overlap"
                )
        return self

    def node_image(self, role: MapImageRole) -> str:
        image = next((x for x in self.images if x.role == role), None)
        if image is None:
            raise ValueError("Explicit original Map image role required")
        root = (
            self.files.node_root
            if self.readonly_inputs is None
            else self.readonly_inputs.source_node_root
        )
        return str(PurePosixPath(root) / "image" / image.file.path)

    def node_tree(self, role: MapTreeRole) -> str:
        if role not in TREE_ROLES:
            raise ValueError("Explicit original Map tree role required")
        root = self.files.node_root
        if role == "routing" and self.readonly_inputs is not None:
            root = self.readonly_inputs.source_node_root
        return str(PurePosixPath(root) / "input" / role)
