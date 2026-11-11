"""Complete selected persistent file observation, not restoration permission."""

from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import Field, model_validator
from .validation import Contract
from .release import ReleaseFile


class MapPersistentState(Contract):
    schema_version: Literal["map-persistent-files/1"] = "map-persistent-files/1"
    baseline_json: str = Field(min_length=1, max_length=16 * 1024 * 1024)
    files: tuple[ReleaseFile, ...] = Field(max_length=100000)

    @model_validator(mode="after")
    def original_files(self) -> Self:
        names = [f.path for f in self.files]
        if len(set(names)) != len(names) or any(
            len(PurePosixPath(n).parts) < 2
            or PurePosixPath(n).parts[0] not in ("storage", "public")
            for n in names
        ):
            raise ValueError(
                "Complete distinct original persistent file paths required"
            )
        expected = sorted(n for n in names if n.startswith("storage/")) + sorted(
            n for n in names if n.startswith("public/")
        )
        if names != expected:
            raise ValueError("Original storage then public file ordering required")
        return self
