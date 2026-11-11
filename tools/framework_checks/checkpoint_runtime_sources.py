"""Exact external caller pins from the existing bounded runtime-input receipts.

This supplements a passed framework receipt's core inventory. It checks only
declared caller files, never installation, a live owner or execution permission.
"""

from pathlib import Path
from typing import Any
import re

SHA = re.compile(r"^[0-9a-f]{64}$")


def runtime_source_pins(
    definition: dict[str, Any],
    framework_pin: dict[str, Any],
    framework: dict[str, Any],
    document: Any,
) -> dict[str, str]:
    if set(definition) != {"receipt", "before", "after", "files"}:
        raise ValueError("Exact original external runtime source mapping required")
    directory = Path(framework_pin["path"]).parent
    values = {}
    for name, filename in (
        ("receipt", "runtime-inputs-acceptance.json"),
        ("before", "runtime-inputs-before.json"),
        ("after", "runtime-inputs-after.json"),
    ):
        pin = definition[name]
        if not isinstance(pin, dict) or pin.get("path") != str(directory / filename):
            raise ValueError("External source receipt left original check directory")
        values[name], _ = document(pin)
    accepted, before, after = values["receipt"], values["before"], values["after"]
    if (
        not isinstance(accepted, dict)
        or accepted.get("passed") is not True
        or accepted.get("unchanged") is not True
        or type(accepted.get("job_id")) is not str
        or accepted["job_id"] != framework.get("job_id")
        or not isinstance(before, dict)
        or not before
        or before != after
        or accepted.get("files") != before
        or any(
            not isinstance(name, str)
            or not isinstance(sha, str)
            or not SHA.fullmatch(sha)
            for name, sha in before.items()
        )
    ):
        raise ValueError("Original stable runtime source proof required")
    imports = accepted.get("actual_imports")
    if not isinstance(imports, dict) or not imports:
        raise ValueError("Actual external runtime module origins required")
    for origin in imports.values():
        if (
            not isinstance(origin, dict)
            or set(origin) != {"path", "sha256"}
            or not isinstance(origin["path"], str)
            or origin["path"] not in before
            or before[origin["path"]] != origin["sha256"]
        ):
            raise ValueError("External runtime module origin differs from source pins")
    selected = definition["files"]
    if (
        not isinstance(selected, list)
        or not 0 < len(selected) <= 4096
        or any(not isinstance(name, str) for name in selected)
        or len(set(selected)) != len(selected)
        or any(name not in before for name in selected)
    ):
        raise ValueError("Exact covered external source file scope required")
    return {name: before[name] for name in selected}
