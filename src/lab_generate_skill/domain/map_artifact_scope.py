"""Shared physical file restrictions; concrete plans separately bind task semantics."""

from pathlib import PurePosixPath
from .lifecycle import AllocationToken
from .state_scope import StateScope


def check_artifact_scope(
    scope: StateScope,
    token: AllocationToken,
    producer: str,
    workspace_root: str,
    private_root: str,
    max_file_bytes: int,
    max_total_bytes: int,
) -> None:
    if token.owner != scope.owner:
        raise ValueError("Map artifact changed original owner")
    expected = (
        ("browser", "attempt", scope.attempt_id)
        if producer == "browser_process"
        else ("site", "batch", None)
    )
    if (token.resource_kind, token.scope, token.attempt_id) != expected:
        raise ValueError("Map artifact producer differs from original resource")
    w, p = PurePosixPath(workspace_root), PurePosixPath(private_root)
    if p == w or not p.is_relative_to(w) or max_file_bytes > max_total_bytes:
        raise ValueError("Map private root/budget outside declared workspace")
