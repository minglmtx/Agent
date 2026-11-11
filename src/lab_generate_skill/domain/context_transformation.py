"""Full deterministic transformation audit, separate from model-visible bytes."""

import hashlib
from typing import Literal, Self
from pydantic import Field, model_validator, field_validator
from .context_budget import ContextRole
from .context_projection import ProjectionKind
from .evidence import EvidenceRef
from .validation import Contract, Identifier, Sha256


class ContextChange(Contract):
    operation: Literal[
        "layout",
        "omit_duplicate",
        "remove_empty_id",
        "share_exact_body",
        "select_source_ranges",
    ]
    source_path: str = Field(min_length=1, max_length=4096, pattern=r"^/")
    target_path: str | None = Field(min_length=1, max_length=4096, pattern=r"^/")
    source_sha256: Sha256
    target_sha256: Sha256 | None
    related_source_paths: tuple[str, ...] = Field(max_length=64)
    reason_code: Identifier

    @field_validator("source_path", "target_path")
    @classmethod
    def safe_coordinate(cls, value: str | None) -> str | None:
        if value is not None and any(c in value for c in ("\0", "\r", "\n")):
            raise ValueError(
                "Transformation coordinates cannot contain control characters"
            )
        return value

    @model_validator(mode="after")
    def complete_mapping(self) -> Self:
        if (self.target_path is None) != (self.target_sha256 is None):
            raise ValueError(
                "Target path/hash must describe the same retained fragment"
            )
        if self.operation == "omit_duplicate" and (
            self.target_path is not None or not self.related_source_paths
        ):
            raise ValueError("Omitted duplicate requires its complete original anchor")
        if any(
            not path.startswith("/") or "\0" in path or len(path) > 4096
            for path in self.related_source_paths
        ) or len(set(self.related_source_paths)) != len(self.related_source_paths):
            raise ValueError("Unique bounded source coordinates required")
        return self


class ContextTransformAudit(Contract):
    schema_version: Literal[
        "context-transform-audit/1", "context-transform-audit/2"
    ] = "context-transform-audit/1"
    role: ContextRole
    source_ref: EvidenceRef
    policy_sha256: Sha256
    kind: ProjectionKind
    input_sha256: Sha256
    no_op_reason: Identifier | None
    changes: tuple[ContextChange, ...] = Field(max_length=100000)

    @model_validator(mode="after")
    def complete_role_audit(self) -> Self:
        adaptive = self.schema_version == "context-transform-audit/2"
        expected = (
            ("public", "actor-public-turn/2" if adaptive else "actor-public-turn/1")
            if self.role == "actor"
            else ("teacher", "teacher-input/1")
        )
        if (self.source_ref.visibility, self.source_ref.content_schema) != expected:
            raise ValueError(
                "Transformation only references original role-allowed source"
            )
        if adaptive and (
            self.role != "actor" or self.kind not in ("compact_full_ax", "local_ax")
        ):
            raise ValueError("Adaptive source audit cannot inherit another role/format")
        if not adaptive and any(
            change.operation == "select_source_ranges" for change in self.changes
        ):
            raise ValueError(
                "Original full-input audit cannot hide partial source selection"
            )
        if bool(self.changes) == (self.no_op_reason is not None):
            raise ValueError("No-op reason required exactly when no transform occurred")
        if self.kind == "identity" and self.changes:
            raise ValueError("Identity cannot contain hidden transformations")
        if len(self.model_dump_json().encode()) > 64 * 1024**2:
            raise ValueError("Complete audit exceeds full evidence byte bound")
        return self


def context_bytes_sha(raw: bytes) -> str:
    if type(raw) is not bytes:
        raise TypeError("Exact bytes required for transformation identity")
    return hashlib.sha256(raw).hexdigest()
