"""Read original checkpoint conditions; never authorize or replay an operation.

The original group plan declares the exact source/input scope and evidence.
Only that scope is compared. Parameter changes remain member binding work;
missing/changed conditions never imply rebuilding an entire website source.
"""

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any
from .checkpoint_runtime_sources import runtime_source_pins

MAX_BYTES = 16 * 1024**2
SHA = re.compile(r"^[0-9a-f]{64}$")


def _raw(path: Path, workspace: Path) -> bytes:
    if (
        not path.is_absolute()
        or path.resolve(strict=True) != path
        or not path.is_relative_to(workspace)
        or not path.is_file()
        or path.stat().st_size > MAX_BYTES
    ):
        raise ValueError("Checkpoint condition input is not canonical/bounded")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Checkpoint condition input exceeds its byte bound")
    return raw


def _pin_key(pin: dict[str, Any]) -> tuple[str, str]:
    if (
        set(pin) != {"path", "sha256"}
        or not isinstance(pin["path"], str)
        or not isinstance(pin["sha256"], str)
        or not SHA.fullmatch(pin["sha256"])
    ):
        raise ValueError("Exact original condition document pin required")
    return pin["path"], pin["sha256"]


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate checkpoint condition field")
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    raise ValueError("Nonfinite checkpoint condition value")


def _document(pin: dict[str, Any], read: Any) -> tuple[object, str]:
    _pin_key(pin)
    raw = read(Path(pin["path"]))
    digest = hashlib.sha256(raw).hexdigest()
    if digest != pin["sha256"]:
        raise ValueError("Checkpoint condition document changed: " + pin["path"])
    return (
        json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        ),
        digest,
    )


def _escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _changes(old: object, new: object, path: str = "") -> list[tuple[str, bool]]:
    """The boolean permits only existing, same-type scalar parameter leaves."""
    if type(old) is not type(new):
        return [(path, False)]
    if isinstance(old, dict) and isinstance(new, dict):
        result = []
        for key in sorted(old.keys() | new.keys()):
            selected = path + "/" + _escape(key)
            if key not in old or key not in new:
                result.append((selected, False))
            else:
                result.extend(_changes(old[key], new[key], selected))
        return result
    if isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new):
            return [(path, False)]
        return [
            change
            for index, (a, b) in enumerate(zip(old, new, strict=True))
            for change in _changes(a, b, path + "/" + str(index))
        ]
    return (
        []
        if old == new
        else [(path, type(old) in (str, int, float) and type(new) in (str, int, float))]
    )


def _verify_checkpoint(
    row: dict[str, Any],
    workspace: Path,
    environment_key: str,
    read: Any,
    document: Any,
) -> dict[str, Any]:
    """Verify declared immutable conditions; all live gates remain separate."""
    definition = row.get("verification")
    if definition is None:
        return {
            "status": "unverified",
            "reason": "Missing exact condition mapping; supplement mapping/verification only",
            "minimum_scope": [row["id"]],
        }
    required = {
        "receipt",
        "source_root",
        "source_files",
        "inputs",
        "minimum_scope",
    }
    if not required <= set(definition) or set(definition) - required - {
        "external_sources"
    }:
        raise ValueError("Incomplete or unknown checkpoint verification fields")
    receipt, receipt_digest = document(definition["receipt"])
    if not isinstance(receipt, dict) or (
        receipt.get("schema_version") != "framework-check/3"
        or receipt.get("passed") is not True
        or receipt.get("source_stable_during_checks") is not True
    ):
        raise ValueError("Stable passed original framework receipt required")
    file_pins = receipt.get("files")
    if not isinstance(file_pins, dict):
        raise ValueError("Original receipt source inventory has an invalid type")
    root = Path(definition["source_root"])
    if (
        not root.is_absolute()
        or root.resolve(strict=True) != root
        or not root.is_relative_to(workspace)
    ):
        raise ValueError("Actual canonical source root required")
    names = definition["source_files"]
    if (
        not isinstance(names, list)
        or not 0 < len(names) <= 4096
        or len(set(names)) != len(names)
    ):
        raise ValueError("Exact nonempty checkpoint source scope required")
    changed: list[dict[str, str]] = []
    for name in names:
        relative = PurePosixPath(name)
        if (
            relative.is_absolute()
            or str(relative) != name
            or ".." in relative.parts
            or name == "."
        ):
            raise ValueError("Canonical relative source file required")
        expected = file_pins.get(name)
        if not isinstance(expected, str) or not SHA.fullmatch(expected):
            raise ValueError("Original receipt does not cover selected source: " + name)
        actual = hashlib.sha256(read(root / name)).hexdigest()
        if actual != expected:
            changed.append({"condition": "implementation", "input": name})
    external = {}
    if "external_sources" in definition:
        external = runtime_source_pins(
            definition["external_sources"], definition["receipt"], receipt, document
        )
        for name, expected in external.items():
            actual = hashlib.sha256(read(Path(name))).hexdigest()
            if actual != expected:
                changed.append({"condition": "external_implementation", "input": name})
    expected_environment = receipt.get("environment_key")
    if not isinstance(expected_environment, str) or not SHA.fullmatch(
        expected_environment
    ):
        raise ValueError("Original full environment identity required")
    if expected_environment != environment_key:
        changed.append(
            {
                "condition": "environment",
                "input": "frozen Python/dependencies/configured check environment",
            }
        )
    parameters: list[dict[str, str]] = []
    inputs = definition["inputs"]
    if not isinstance(inputs, list) or len(inputs) > 32:
        raise ValueError("Bounded contract/configuration/branch input scope required")
    seen = set()
    for item in inputs:
        if (
            set(item) != {"name", "expected", "current", "parameter_paths"}
            or not isinstance(item["name"], str)
            or item["name"] in seen
        ):
            raise ValueError("Unique exact input condition required")
        seen.add(item["name"])
        allowed = item["parameter_paths"]
        if (
            not isinstance(allowed, list)
            or len(set(allowed)) != len(allowed)
            or any(
                not isinstance(path, str)
                or not path.startswith("/")
                or len(path) > 1024
                for path in allowed
            )
        ):
            raise ValueError("Exact scalar parameter JSON pointers required")
        old, _ = document(item["expected"])
        new, _ = document(item["current"])
        for path, scalar in _changes(old, new):
            schema_field = path.rsplit("/", 1)[-1] in {
                "schema_version",
                "content_schema",
                "contract_version",
                "$schema",
            }
            target = (
                parameters
                if scalar and path in allowed and not schema_field
                else changed
            )
            target.append({"condition": item["name"], "input": path or "/"})
    scope = definition["minimum_scope"]
    if (
        not isinstance(scope, list)
        or not scope
        or any(not isinstance(x, str) or not x for x in scope)
    ):
        raise ValueError("Explicit minimum affected checkpoint/consumer scope required")
    return {
        "status": "changed" if changed else "matched",
        "reason": "Exact declared source/environment/input conditions compared",
        "receipt": definition["receipt"]["path"],
        "receipt_sha256": receipt_digest,
        "source_file_count": len(names),
        "external_source_file_count": len(external),
        "changed_conditions": changed,
        "member_parameter_checks": parameters,
        "minimum_scope": scope,
        "runtime_or_resume_authority": False,
    }


def verify_checkpoints(
    rows: list[dict[str, Any]],
    workspace: Path,
    environment_key: str,
) -> dict[str, Any]:
    """One invocation reads each immutable body once; no persistent cache."""
    if not workspace.is_absolute() or workspace.resolve(strict=True) != workspace:
        raise ValueError("Canonical workspace required")
    if not SHA.fullmatch(environment_key):
        raise ValueError("Actual complete environment identity required")
    raw_cache: dict[Path, bytes] = {}
    documents: dict[tuple[str, str], tuple[object, str]] = {}
    total = 0

    def read(path: Path) -> bytes:
        nonlocal total
        if path not in raw_cache:
            value = _raw(path, workspace)
            total += len(value)
            if total > 64 * 1024**2 or len(raw_cache) >= 8192:
                raise ValueError("Checkpoint comparison exceeds invocation read budget")
            raw_cache[path] = value
        return raw_cache[path]

    def document(pin: dict[str, Any]) -> tuple[object, str]:
        key = _pin_key(pin)
        if key not in documents:
            documents[key] = _document(pin, read)
        return documents[key]

    result: dict[str, Any] = {}
    try:
        for row in rows:
            if row["id"] in result:
                raise ValueError("Duplicate checkpoint condition identity")
            try:
                result[row["id"]] = _verify_checkpoint(
                    row, workspace, environment_key, read, document
                )
            except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
                result[row["id"]] = {
                    "status": "unverified",
                    "reason": str(error),
                    "minimum_scope": [row["id"]],
                }
        return {
            "rows": result,
            "all_declared_conditions_matched": bool(result)
            and all(v["status"] == "matched" for v in result.values()),
            "body_reads": len(raw_cache),
            "bytes_read": total,
            "scope": "Only exact original-plan source/environment/input conditions. Member binding and live rights/state/claim/closure remain required; no test, task or recovery is executed.",
            "runtime_or_resume_authority": False,
        }
    finally:
        raw_cache.clear()
        documents.clear()
