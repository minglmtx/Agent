"""Complete original Postmill digest/schema/media facts, private and not rights."""

from pathlib import PurePosixPath
import re
import hashlib
from typing import Annotated, Literal, Self
from uuid import UUID
from pydantic import Field, JsonValue, model_validator, field_validator
from lab_generate_skill.domain.validation import Contract, Sha256

TABLES12 = frozenset(
    {
        "forums",
        "comments",
        "submission_votes",
        "comment_votes",
        "wiki_pages",
        "wiki_revisions",
        "forum_tags",
        "forums_tags",
        "hidden_forums",
        "forum_subscriptions",
        "user_blocks",
        "users",
    }
)
NATIVE13 = TABLES12 | {"submissions"}
NAME = re.compile(r"[a-z][a-z0-9_]{0,62}")
NativeId = Annotated[int, Field(ge=1, le=2**63 - 1)]


def canonical_uuid(value: str) -> str:
    if str(UUID(value)) != value:
        raise ValueError("Canonical original native UUID required")
    return value


def native_columns(columns: tuple[str, ...]) -> None:
    if (
        not columns
        or len(columns) != len(set(columns))
        or any(NAME.fullmatch(c) is None for c in columns)
    ):
        raise ValueError("Complete unique native columns required")


def relative_media_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or str(path) != value
        or value == "."
        or ".." in path.parts
        or any(ord(c) < 32 or c == "\\" for c in value)
    ):
        raise ValueError("Canonical relative native media path required")
    return value


class NativeDigest(Contract):
    count: int = Field(ge=0, le=2**63 - 1)
    digest: str = Field(pattern=r"^[0-9a-f]{32}$")


class SubmissionDigest(Contract):
    count: int = Field(ge=0, le=2**63 - 1)
    columns: tuple[str, ...] = Field(min_length=1, max_length=512)
    key: tuple[Literal["id"]]
    sha256: Sha256

    @model_validator(mode="after")
    def native_column_set(self) -> Self:
        native_columns(self.columns)
        if "id" not in self.columns:
            raise ValueError("Original indexed native id column required")
        if self.count == 0 and self.sha256 != hashlib.sha256(b"").hexdigest():
            raise ValueError("Exact empty native submission checksum required")
        return self


class Complete13(Contract):
    version: Literal["reddit45-readonly-complete13-v1"]
    twelve_task_tables: dict[str, NativeDigest]
    submissions: SubmissionDigest
    users_only_ignored_column: Literal["last_seen"]

    @model_validator(mode="after")
    def all_tables(self) -> Self:
        if set(self.twelve_task_tables) != TABLES12:
            raise ValueError("Every original protected12 table required")
        return self


class AuxiliaryDigest(NativeDigest):
    columns: tuple[str, ...] = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def native_column_set(self) -> Self:
        native_columns(self.columns)
        return self


class AuxiliaryState(Contract):
    all_public_tables: tuple[str, ...] = Field(min_length=14, max_length=512)
    all_public_schemas: dict[str, tuple[str, ...]]
    auxiliary: dict[str, AuxiliaryDigest]
    excluded_only_new_image_id: str | None

    @model_validator(mode="after")
    def complete_schema(self) -> Self:
        names = self.all_public_tables
        if (
            len(set(names)) != len(names)
            or not NATIVE13 | {"images"} <= set(names)
            or any(NAME.fullmatch(n) is None for n in names)
        ):
            raise ValueError("Complete unique native public table list required")
        if (
            set(self.all_public_schemas) != set(names)
            or set(self.auxiliary) != set(names) - NATIVE13
        ):
            raise ValueError("Every original auxiliary table/schema required")
        for columns in self.all_public_schemas.values():
            native_columns(columns)
        if set(self.all_public_schemas["images"]) != {
            "id",
            "file_name",
            "sha256",
            "width",
            "height",
        }:
            raise ValueError("Original complete native images schema required")
        if any(
            row.columns != self.all_public_schemas[name]
            for name, row in self.auxiliary.items()
        ):
            raise ValueError("Auxiliary digest omitted a native column")
        if self.excluded_only_new_image_id is not None:
            canonical_uuid(self.excluded_only_new_image_id)
        return self


class NativeImage(Contract):
    id: str
    file_name: str = Field(min_length=1, max_length=1024)
    sha256: Sha256
    width: int = Field(gt=0, le=1000000)
    height: int = Field(gt=0, le=1000000)

    @field_validator("id")
    @classmethod
    def uuid(cls, value: str) -> str:
        return canonical_uuid(value)


class MediaFile(Contract):
    bytes: int = Field(ge=0, le=2 * 1024**4)
    sha256: Sha256
    format: str | None = None
    dimensions: tuple[int, int] | None = None

    @model_validator(mode="after")
    def image_metadata(self) -> Self:
        if (self.format is None) != (self.dimensions is None):
            raise ValueError("Image format and dimensions must both be recorded")
        if self.dimensions is not None and any(
            not 0 < x <= 1000000 for x in self.dimensions
        ):
            raise ValueError("Actual positive image dimensions required")
        return self


class NativeMedia(Contract):
    version: Literal["reddit-native-media-storage-candidate-v2"]
    directories: tuple[str, ...] = Field(max_length=100000)
    files: dict[str, MediaFile]

    @model_validator(mode="after")
    def relative_tree(self) -> Self:
        if tuple(sorted(set(self.directories))) != self.directories:
            raise ValueError("Unique sorted native media directories required")
        for name in [*self.directories, *self.files]:
            relative_media_path(name)
        if any(
            name.lower().endswith((".jpg", ".jpeg"))
            and (value.format is None or value.dimensions is None)
            for name, value in self.files.items()
        ):
            raise ValueError("Full original JPEG metadata required")
        if set(self.directories) & set(self.files):
            raise ValueError("A media file cannot also be a directory")
        return self


class VoteScope(Contract):
    original: NativeDigest
    new_post_votes: tuple[dict[str, JsonValue], ...] = Field(max_length=100000)
    excluded_only_new_post_id: NativeId | None


class DatabaseCapture(Contract):
    complete13: Complete13
    all_original_submissions: SubmissionDigest
    auxiliary: AuxiliaryState
    added_posts: tuple[dict[str, JsonValue], ...] = Field(max_length=100000)
    attached_image: NativeImage | None
    full_original_vote_scope: VoteScope

    @model_validator(mode="after")
    def schemas_agree(self) -> Self:
        if (
            self.complete13.submissions.columns
            != self.auxiliary.all_public_schemas["submissions"]
            or self.all_original_submissions.columns
            != self.complete13.submissions.columns
        ):
            raise ValueError("Every native post column must agree across captures")
        if any(
            set(post) != set(self.complete13.submissions.columns)
            for post in self.added_posts
        ):
            raise ValueError("Full actual new post rows required")
        return self


class NativeCapture(DatabaseCapture):
    native_media: NativeMedia
