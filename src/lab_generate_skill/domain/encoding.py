"""Frozen local MiniLM files/config and numeric output; no model import or I/O."""

import hashlib
from pathlib import PurePosixPath
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from .validation import Contract, NonEmptyText, Sha256


class EncoderFile(Contract):
    path: NonEmptyText
    sha256: Sha256
    size_bytes: int = Field(ge=0)

    @field_validator("path")
    @classmethod
    def relative_regular_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            not path.parts
            or path.is_absolute()
            or path.as_posix() != value
            or any(p in (".", "..") or p.startswith(".") for p in path.parts)
            or "\\" in value
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
        ):
            raise ValueError(
                "Encoder member must be a canonical nonhidden relative path"
            )
        return value


class EncoderFiles(Contract):
    schema_version: Literal["encoder-files/1"] = "encoder-files/1"
    model_id: Literal["sentence-transformers/all-MiniLM-L6-v2"] = (
        "sentence-transformers/all-MiniLM-L6-v2"
    )
    files: tuple[EncoderFile, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def complete(self) -> Self:
        names = [f.path for f in self.files]
        if names != sorted(set(names)):
            raise ValueError("Encoder members must be sorted and unique")
        if not {
            "model.safetensors",
            "modules.json",
            "tokenizer.json",
            "config.json",
            "1_Pooling/config.json",
        } <= set(names):
            raise ValueError("Incomplete MiniLM model manifest")
        return self

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class EncoderPackage(Contract):
    name: Literal[
        "numpy", "sentence-transformers", "tokenizers", "torch", "transformers"
    ]
    version: NonEmptyText


class EncoderConfig(Contract):
    schema_version: Literal["encoder-config/1"] = "encoder-config/1"
    method: Literal["minilm-cpu-full-eligible-v1"] = "minilm-cpu-full-eligible-v1"
    packages: tuple[EncoderPackage, ...]
    cpu_threads: int = Field(ge=1, le=64)
    max_documents: int = Field(ge=6, le=100000)
    max_input_bytes: int = Field(ge=1, le=256 * 1024 * 1024)
    batch_size: Literal[32] = 32
    dimensions: Literal[384] = 384

    @field_validator("batch_size", "dimensions", mode="before")
    @classmethod
    def exact_integer(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Encoder constants require exact integers")
        return value

    @model_validator(mode="after")
    def pinned_packages(self) -> Self:
        if [p.name for p in self.packages] != [
            "numpy",
            "sentence-transformers",
            "tokenizers",
            "torch",
            "transformers",
        ]:
            raise ValueError(
                "Encoder requires all five package versions in canonical order"
            )
        return self


class EncodedScores(Contract):
    schema_version: Literal["encoded-scores/1"] = "encoded-scores/1"
    model_files_sha256: Sha256
    config_sha256: Sha256
    documents_sha256: Sha256
    query_sha256: Sha256
    document_vectors_sha256: Sha256
    query_vector_sha256: Sha256
    scores: tuple[float, ...] = Field(min_length=1)
    documents_reused: bool

    @field_validator("scores")
    @classmethod
    def finite_scores(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        import math

        if not all(math.isfinite(x) for x in value):
            raise ValueError("Encoder scores must be finite")
        return value
