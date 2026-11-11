"""Finite candidate identities; policy3 adds a preferred initial navigation view."""

from typing import Literal

ADAPTIVE_POLICY_SCHEMAS = (
    "context-projection-policy/2",
    "context-projection-policy/3",
)


def adaptive_candidate_ids(
    policy_version: str, *, active_read: bool, local_supported: bool = True
) -> tuple[str, ...]:
    if policy_version not in ADAPTIVE_POLICY_SCHEMAS:
        raise ValueError("Explicit supported adaptive policy required")
    if active_read:
        if not local_supported:
            raise ValueError("An unsupported source cannot have an active reading")
        return ("local_ax",)
    if not local_supported:
        return ("compact_full_ax",)
    if policy_version == "context-projection-policy/3":
        return ("compact_full_ax", "local_ax_navigation", "local_ax")
    return ("compact_full_ax", "local_ax")


def adaptive_candidate_kind(
    candidate_id: str,
) -> Literal["compact_full_ax", "local_ax"]:
    if candidate_id == "compact_full_ax":
        return "compact_full_ax"
    if candidate_id in ("local_ax_navigation", "local_ax"):
        return "local_ax"
    raise ValueError("Unknown adaptive candidate identity")
