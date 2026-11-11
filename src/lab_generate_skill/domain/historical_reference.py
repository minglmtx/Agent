"""Exact historical location/content mappings; never permission to execute code."""

from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import Field, field_validator, model_validator
from .validation import Contract, Sha256


class HistoricalKey(Contract):
    original_path: str = Field(min_length=1, max_length=4096)
    sha256: Sha256

    @field_validator("original_path")
    @classmethod
    def literal_absolute_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            not path.is_absolute()
            or str(path) != value
            or ".." in path.parts
            or "\\" in value
            or any(ord(c) < 32 for c in value)
        ):
            raise ValueError("Historical location must be a canonical absolute path")
        return value


class HistoricalFile(Contract):
    key: HistoricalKey
    relative_path: str
    size_bytes: int = Field(ge=0, le=512 * 1024 * 1024)

    @model_validator(mode="after")
    def bounded_content_location(self) -> Self:
        p = PurePosixPath(self.relative_path)
        if (
            str(p) != self.relative_path
            or len(p.parts) != 3
            or p.parts[:2] != ("records", self.key.sha256)
            or p.name in (".", "..")
            or "\\" in self.relative_path
            or any(ord(c) < 32 for c in self.relative_path)
        ):
            raise ValueError("Historical copy must be records/SHA256/filename")
        return self


class HistoricalReferenceMap(Contract):
    schema_version: Literal["historical-reference-map/1"] = "historical-reference-map/1"
    files: tuple[HistoricalFile, ...] = Field(min_length=1, max_length=20000)

    @model_validator(mode="after")
    def exact_unique_keys(self) -> Self:
        keys = [(f.key.original_path, f.key.sha256) for f in self.files]
        if len(set(keys)) != len(keys):
            raise ValueError(
                "Historical mapping contains duplicate original path/digest"
            )
        sizes: dict[str, int] = {}
        for file in self.files:
            previous = sizes.setdefault(file.relative_path, file.size_bytes)
            if previous != file.size_bytes:
                raise ValueError("One content object has inconsistent sizes")
        return self
