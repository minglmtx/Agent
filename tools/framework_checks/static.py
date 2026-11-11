"""Reuse successful static commands only for identical frozen inputs."""

from collections.abc import Callable
import json
from pathlib import Path
from typing import Any
from framework_checks.cache import cache_lock, digest, file_digest

Run = Callable[[str, list[str]], int]


def static_checks(
    *,
    cache: Path,
    output: Path,
    files: dict[str, str],
    format_sources: list[str],
    environment: dict[str, object],
    run: Run,
    checks: list[dict[str, object]],
    current_files: Callable[[], dict[str, str]],
    fresh: bool = False,
) -> None:
    key = digest({"version": 1, "files": files, "environment": environment})
    root = cache / "static" / key
    root.mkdir(parents=True, exist_ok=True)
    receipt = root / "receipt.json"
    with cache_lock(root / "lock"):
        if receipt.exists() and not fresh:
            value: Any = json.loads(receipt.read_text())
            if value["key"] != key or value["files"] != files:
                raise ValueError("Static cache identity mismatch")
            if [item["name"] for item in value["checks"]] != [
                "format_check",
                "type_check",
            ]:
                raise ValueError("Incomplete static cache evidence")
            for item in value["checks"]:
                if item["returncode"] != 0:
                    raise ValueError("Failed static check cannot be reused")
                source = Path(value["output"]) / f"{item['name']}.log"
                if file_digest(source) != value["logs"][item["name"]]:
                    raise ValueError("Static evidence log changed")
                (output / source.name).write_bytes(source.read_bytes())
                checks.append(
                    {
                        **item,
                        "execution": "reused",
                        "elapsed_seconds": 0.0,
                        "evidence": str(receipt),
                        "evidence_sha256": file_digest(receipt),
                    }
                )
            return
        start = len(checks)
        run("format_check", ["black", "--check", *format_sources])
        # Compatible incremental cache survives small source/test edits. One
        # writer at a time, independent of the immutable static-result cache.
        mypy = (
            cache
            / "mypy"
            / digest(
                {"environment": environment, "config": files.get("pyproject.toml")}
            )
        )
        with cache_lock(mypy / "lock"):
            run("type_check", ["mypy", "--cache-dir", str(mypy / "data")])
        selected = checks[start:]
        if all(c["returncode"] == 0 for c in selected) and files == current_files():
            value = {
                "key": key,
                "files": files,
                "output": str(output),
                "checks": selected,
                "logs": {
                    str(c["name"]): file_digest(output / f"{c['name']}.log")
                    for c in selected
                },
            }
            # Keep the original accepted cache evidence on forced rechecks.
            if not receipt.exists():
                temporary = root / "receipt.pending"
                temporary.write_text(json.dumps(value, indent=2) + "\n")
                temporary.replace(receipt)
