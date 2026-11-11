"""Persist original member/cleanup facts; no retry or resource authority."""

from collections.abc import Callable
from pathlib import Path
from typing import Any
import json
from lab_generate_skill.adapters.processes.remote_errors import describe_error


def original_site_close_observations(
    primary: BaseException,
) -> tuple[list[dict[str, Any]], bool]:
    """Collect existing physical facts, without reading CAS or granting closure."""
    pending = [primary]
    seen: set[int] = set()
    observations: list[dict[str, Any]] = []
    while pending and len(seen) < 128:
        error = pending.pop(0)
        if id(error) in seen:
            continue
        seen.add(id(error))
        value = getattr(error, "site_resource_physical_observation", None)
        if isinstance(value, dict) and value not in observations:
            observations.append(dict(value))
        if isinstance(error, BaseExceptionGroup):
            pending.extend(error.exceptions)
        for linked in (
            error.__cause__,
            error.__context__,
            getattr(error, "primary", None),
        ):
            if isinstance(linked, BaseException):
                pending.append(linked)
        for linked in getattr(error, "cleanup_errors", ()):
            if isinstance(linked, BaseException):
                pending.append(linked)
    return observations, bool(pending)


def finish_member_metadata(
    output: Path,
    facts: dict[str, Any],
    revoke: Callable[[], None] | None,
    primary: BaseException | None,
) -> None:
    """Revoke even when output fails, retaining both primary and cleanup errors."""
    errors: list[BaseException] = []
    if primary is not None:
        observations, truncated = original_site_close_observations(primary)
        facts["site_resource_physical_observations"] = observations
        facts["site_resource_physical_observations_truncated"] = truncated
    facts["metadata_admission_revoked"] = False
    if revoke is not None:
        try:
            revoke()
            facts["metadata_admission_revoked"] = True
        except BaseException as error:
            facts["metadata_revoke_error"] = describe_error(error).model_dump(
                mode="json"
            )
            errors.append(error)
    try:
        (output / "member-result.json").write_text(json.dumps(facts, indent=2) + "\n")
    except BaseException as error:
        errors.append(error)
    if errors:
        raise BaseExceptionGroup(
            "Original member and metadata finalization",
            ([primary] if primary is not None else []) + errors,
        ) from None
