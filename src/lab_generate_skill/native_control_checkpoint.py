"""Small references to completed native controls; never an admission proof.

The actual verifier must still recompute the saved raw receipts. This index
survives later reset/reference failures without copying large private snapshots.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath

from .io_utils import atomic_write_json

VERSION = "native-control-checkpoint-v1"


def _pin(directory, name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or str(relative) != name:
        raise ValueError("Canonical relative evidence path required")
    root = Path(directory).resolve()
    path = root / name
    if not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError("Local evidence file missing or outside checkpoint")
    if any(p.is_symlink() for p in (path, *path.parents) if p != root and p.is_relative_to(root)):
        raise ValueError("Symlink evidence is not a checkpoint member")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def save_checkpoint(directory, *, source_task_id, expected_controls, completed_controls,
                    final_reset_started=False):
    names = list(expected_controls)
    completed = list(completed_controls)
    if (not names or len(set(names)) != len(names) or len(set(completed)) != len(completed)
            or any(not n or not all(c.isalnum() or c == "_" for c in n) for n in names)
            or not set(completed).issubset(names)):
        raise ValueError("Unique expected and completed control identifiers required")
    paths = ["materialized-contract.json", "private-reference.json"]
    for name in completed:
        paths.extend([f"{name}/native-private-receipt.json", f"reset-{name}.json"])
    if final_reset_started:
        paths.append("final-reset-before-reference.json")
    pins = {name: _pin(directory, name) for name in paths}
    contract = json.loads((Path(directory) / "materialized-contract.json").read_text())
    if contract.get("source_task_id") != source_task_id:
        raise ValueError("Checkpoint source differs from actual contract")
    record = dict(version=VERSION, source_task_id=source_task_id,
                  expected_controls=names, completed_controls=completed,
                  files=pins, final_reset_started=final_reset_started,
                  remaining_controls=[n for n in names if n not in completed],
                  final_reset_verified=False, normal_gate_passed=False,
                  training_admitted=False, raw_control_reverification_required=True)
    atomic_write_json(Path(directory) / "control-checkpoint.json", record)
    return record


def verify_checkpoint(directory):
    """Check file custody only. Do not turn this result into a task reward."""
    row = json.loads((Path(directory) / "control-checkpoint.json").read_text())
    if (row.get("version") != VERSION or row.get("normal_gate_passed") is not False
            or row.get("training_admitted") is not False
            or row.get("final_reset_verified") is not False
            or row.get("raw_control_reverification_required") is not True):
        raise ValueError("Checkpoint must not claim admission or completed reset")
    expected = list(row["expected_controls"]); done = list(row["completed_controls"])
    if len(set(expected)) != len(expected) or len(set(done)) != len(done) or not set(done).issubset(expected):
        raise ValueError("Invalid checkpoint controls")
    required = {"materialized-contract.json", "private-reference.json"}
    for name in done:
        required.update([f"{name}/native-private-receipt.json", f"reset-{name}.json"])
    if row["final_reset_started"]:
        required.add("final-reset-before-reference.json")
    if set(row["files"]) != required or row["remaining_controls"] != [n for n in expected if n not in done]:
        raise ValueError("Incomplete checkpoint member list")
    for name, pin in row["files"].items():
        if _pin(directory, name) != pin:
            raise ValueError("Checkpoint evidence changed: " + name)
    contract = json.loads((Path(directory) / "materialized-contract.json").read_text())
    if contract.get("source_task_id") != row["source_task_id"]:
        raise ValueError("Checkpoint source differs")
    return row
