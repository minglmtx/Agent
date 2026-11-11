"""Private complete search component; not an initial-state or source grant."""

import hashlib
import json
import re
from typing import Annotated, Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract, Sha256
from ..service_contract import ShoppingServiceSpec


class NavigationSearchIndex(Contract):
    documents: int = Field(ge=0, le=1_000_000)
    documents_sha256: Sha256


class NavigationSearchContents(Contract):
    schema_version: Literal["shopping-navigation-search-contents/1"] = (
        "shopping-navigation-search-contents/1"
    )
    search_port: int = Field(ge=1024, le=65535)
    cluster_uuid: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")]
    version: Annotated[str, Field(pattern=r"^7\.[0-9]+\.[0-9]+$")]
    normalization: Literal[
        "original-shopping-search-physical-identity-v1",
        "original-shopping-search-physical-identity-v2",
    ]
    raw_metadata_sha256: Sha256
    metadata_sha256: Sha256
    aliases_sha256: Sha256
    mutation_watermark_sha256: Sha256
    indices: dict[str, NavigationSearchIndex] = Field(max_length=256)
    documents: int = Field(ge=0, le=1_000_000)
    complete_scrolls: Literal[True]
    cleanup_confirmed: Literal[True]

    @model_validator(mode="after")
    def complete(self) -> Self:
        if any(
            not re.fullmatch(r"[a-z0-9.][a-z0-9_.-]{0,254}", name)
            or name in (".", "..")
            for name in self.indices
        ):
            raise ValueError("Literal original search index names required")
        if self.documents != sum(row.documents for row in self.indices.values()):
            raise ValueError("Complete per-index document counts required")
        return self

    def require_service(self, spec: ShoppingServiceSpec) -> None:
        if self.search_port != spec.ports.search:
            raise ValueError("Search measurement changed original service endpoint")

    @property
    def content_sha256(self) -> str:
        # Raw identity and the within-measurement mutation watermark remain in
        # this receipt. They cannot be compared as cross-instance business data.
        body = self.model_dump(
            mode="json",
            include={
                "version",
                "normalization",
                "metadata_sha256",
                "aliases_sha256",
                "indices",
                "documents",
            },
        )
        return hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
