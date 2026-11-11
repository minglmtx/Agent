"""Read-only compute acceptance of the actual historical library and consumers."""

from __future__ import annotations
import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

from lab_generate_skill.bootstrap.historical_reading import open_historical_reader
from lab_generate_skill.domain.historical_reference import (
    HistoricalKey,
    HistoricalReferenceMap,
)
from test_slurm_commands import guard

WORKSPACE = Path("/anvme/workspace/r102bf10-lab-generate-skill")
PROJECT = WORKSPACE / "code/lab-generate-skill"
LIBRARY = WORKSPACE / "archives/legacy-project-reference-library-20261026-v1"
ADMIN = WORKSPACE / "admin/legacy-reference-cutover-20261026-v1"
MAP_SHA = "4e648b223d5eda572a117b4c0dad92c2706338952963320d75d59ead801e220e"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pointer(value: Any, path: str) -> Any:
    for part in path.lstrip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def check(output: Path, software: Path) -> dict[str, Any]:
    accepted = json.loads(software.read_bytes())
    assert accepted["passed"] and accepted["source_stable_during_checks"]
    for name, digest in accepted["files"].items():
        assert sha(PROJECT / name) == digest, name
    blocked: list[str] = []
    prefixes = (
        "/home/vault/r102bf/r102bf10/lab-skill-history",
        "/home/atuin/r102bf/r102bf10/lmtx/outputs",
        "/home/atuin/r102bf/r102bf10/lmtx/TFcode-generate-skill",
    )

    def audit(event: str, args: tuple[Any, ...]) -> None:
        if event == "open" and isinstance(args[0], (str, bytes)):
            name = os.fsdecode(args[0])
            if any(name == p or name.startswith(p + "/") for p in prefixes):
                blocked.append(name)
                raise AssertionError("Historical original path opened: " + name)

    sys.addaudithook(audit)
    map_path = LIBRARY / "historical-read-map-v1.json"
    assert sha(map_path) == MAP_SHA
    mapping = HistoricalReferenceMap.model_validate_json(map_path.read_bytes())
    reader = open_historical_reader(LIBRARY, map_path.name, MAP_SHA, guard(600))
    outputs: dict[tuple[str, str], str] = {}
    total_bytes = 0
    for entry in mapping.files:
        raw = reader.read(entry.key, guard(30))
        assert len(raw) == entry.size_bytes
        assert hashlib.sha256(raw).hexdigest() == entry.key.sha256
        total_bytes += len(raw)
        outputs[(entry.key.original_path, entry.key.sha256)] = str(
            LIBRARY / entry.relative_path
        )
    indexes: dict[str, dict[str, Any]] = {}
    index_hashes: dict[str, str] = {}
    plan_hashes: dict[str, str] = {}
    counts = {"with_original_plan": 0, "without_original_plan": 0}
    resolutions = []
    for line in (LIBRARY / "reference-consumers.jsonl").read_text().splitlines():
        row = json.loads(line)
        for consumer in row["consumers"]:
            if "field" not in consumer:
                continue
            source = consumer["indexed_record"]
            if source not in indexes:
                index_hashes[source] = sha(Path(source))
                records = [json.loads(x) for x in Path(source).read_text().splitlines()]
                indexes[source] = {r["source_task_id"]: r for r in records}
                assert len(indexes[source]) == len(records), "duplicate source index"
            record = indexes[source][consumer["source_task_id"]]
            ref = pointer(record, consumer["field"])
            assert (
                ref["path"] == row["old_path"]
                and ref["sha256"] == consumer["expected_sha256"]
            ), consumer
            key = HistoricalKey(original_path=ref["path"], sha256=ref["sha256"])
            raw = reader.read(key, guard(30))
            assert hashlib.sha256(raw).hexdigest() == key.sha256
            pin = consumer.get("original_plan")
            if pin:
                path = pin["path"]
                if path not in plan_hashes:
                    plan_hashes[path] = sha(Path(path))
                assert plan_hashes[path] == pin["sha256"], path
                counts["with_original_plan"] += 1
            else:
                counts["without_original_plan"] += 1
            resolutions.append(
                {
                    **consumer,
                    "old_path": key.original_path,
                    "workspace_path": outputs[(key.original_path, key.sha256)],
                    "status": "original_bytes_read_via_workspace_port",
                    "runtime_execution_cutover": False,
                }
            )
    for path, digest in {**index_hashes, **plan_hashes}.items():
        assert sha(Path(path)) == digest, path
    cutover = json.loads((ADMIN / "document-cutover.json").read_bytes())
    for doc in cutover["documents"]:
        assert sha(Path(doc["path"])) == doc["after_sha256"]
    for change in cutover["applied_changes"]:
        body = Path(change["document"]).read_text()
        assert change["old_path"] not in body, change["old_path"]
        assert change["replacement"] in body, change["replacement"]
    example = next(
        f
        for f in mapping.files
        if f.key.sha256
        == "8eddfcfa825cdf3e7f9c812735d88fac02156d02ffb28acb29cfe291a137fb48"
    )
    command = [
        sys.executable,
        "-B",
        str(PROJECT / "tools/read_historical_reference.py"),
        "--root",
        str(LIBRARY),
        "--map",
        map_path.name,
        "--map-sha256",
        MAP_SHA,
        "--original-path",
        example.key.original_path,
        "--sha256",
        example.key.sha256,
    ]
    completed = subprocess.run(command, capture_output=True, timeout=60, check=True)
    assert hashlib.sha256(completed.stdout).hexdigest() == example.key.sha256
    assert not completed.stderr
    for name, digest in accepted["files"].items():
        assert sha(PROJECT / name) == digest, name
    assert not blocked
    (output / "consumer-resolution.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in resolutions)
    )
    (output / "unchanged-inputs.json").write_text(
        json.dumps({"indexes": index_hashes, "plans": plan_hashes}, indent=2) + "\n"
    )
    return {
        "passed": True,
        "mapped_versions_read": len(mapping.files),
        "mapped_bytes_read_including_duplicates": total_bytes,
        "consumer_references_read": len(resolutions),
        "consumer_plan_presence": counts,
        "distinct_original_plans_unchanged": len(plan_hashes),
        "indexes_unchanged": index_hashes,
        "document_changes_verified": len(cutover["applied_changes"]),
        "documents_verified": len(cutover["documents"]),
        "old_path_open_attempts": blocked,
        "cli_exact_bytes": True,
        "map_sha256": MAP_SHA,
        "software_receipt": str(software),
        "software_receipt_sha256": sha(software),
        "software_job": accepted["job_id"],
        "files": accepted["files"],
        "source_stable": True,
        "old_locations_deleted": False,
        "runtime_execution_cutover": False,
        "whole_legacy_tree_retirement_approved": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--software", required=True, type=Path)
    args = parser.parse_args()
    job = os.environ["SLURM_JOB_ID"]
    output = ADMIN / ("verify-" + job)
    output.mkdir(exist_ok=False)
    try:
        result = check(output, args.software)
    except BaseException:
        (output / "traceback.txt").write_text(traceback.format_exc())
        (output / "result.json").write_text(
            json.dumps(
                {
                    "passed": False,
                    "job_id": job,
                    "host": socket.gethostname(),
                    "traceback": str(output / "traceback.txt"),
                },
                indent=2,
            )
            + "\n"
        )
        raise
    result.update(job_id=job, host=socket.gethostname())
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ("files", "indexes_unchanged")}
        )
    )


if __name__ == "__main__":
    main()
