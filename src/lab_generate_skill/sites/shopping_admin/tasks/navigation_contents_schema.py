"""Pure measured navigation contents, retaining independent physical identities.

Version2 projects only verified original startup config port/timestamps and
explicit search runtime identity. Raw original recovery bytes remain pinned.
"""

import hashlib
from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract, Sha256
from ..state_contract import AdminStateSnapshot


class NavigationContentsReply(Contract):
    schema_version: Literal["admin-navigation-contents-reply/2"] = (
        "admin-navigation-contents-reply/2"
    )
    database_raw_sha256: Sha256
    database_content_sha256: Sha256
    database_content_bytes: int = Field(ge=100)
    search_metadata_sha256: Sha256
    search_documents_sha256: Sha256
    search_documents: int = Field(ge=0, le=1_000_000)


class NavigationContents(Contract):
    schema_version: Literal["admin-navigation-contents/2"] = (
        "admin-navigation-contents/2"
    )
    snapshot_sha256: Sha256
    image_sha256: Sha256
    measured: NavigationContentsReply
    # Paths are complete, sorted and pinned by the original state snapshot.
    artifacts: tuple[tuple[str, Sha256 | None], ...]

    @model_validator(mode="after")
    def complete(self) -> Self:
        from ..artifact_contract import ARTIFACT_PATHS

        if tuple(p for p, _ in self.artifacts) != tuple(sorted(ARTIFACT_PATHS)):
            raise ValueError(
                "Navigation contents require the full original artifact scope"
            )
        return self

    def require_snapshot(self, snapshot: AdminStateSnapshot) -> None:
        if (
            self.snapshot_sha256,
            self.image_sha256,
            self.measured.database_raw_sha256,
            self.artifacts,
        ) != (
            snapshot.digest,
            snapshot.plan.service.layout.image_sha256,
            snapshot.database.sha256,
            tuple(zip(snapshot.artifacts.layout.paths, snapshot.artifacts.tree_sha256)),
        ):
            raise ValueError(
                "Navigation contents changed the original measured snapshot"
            )

    @property
    def content_sha256(self) -> str:
        # Raw dump SHA and snapshot identity include physical/time identity;
        # keep them in the proof, outside this explicit content projection.
        value = {
            "policy": self.schema_version,
            "image_sha256": self.image_sha256,
            "measured": self.measured.model_dump(
                mode="json", exclude={"database_raw_sha256"}
            ),
            "artifacts": self.artifacts,
        }
        import json

        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
