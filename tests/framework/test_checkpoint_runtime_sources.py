"""External production caller pins and per-member inputs on the existing CLI."""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
import pytest
from framework_checks.cache import digest
from framework_checks.environment import environment_identity
from framework_checks.checkpoint_conditions import verify_checkpoints
from test_checkpoint_conditions import sample, pin, ENV, W


def external_case(root: Path) -> dict[str, Any]:
    row, _, _ = sample(root)
    runtime = root / "runtime"
    runtime.mkdir()
    entry, configuration = runtime / "entry.py", runtime / "budgets.json"
    entry.write_text("current_entry = True\n")
    configuration.write_text('{"schema_version":"budgets/2","task_seconds":10}')
    files = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (entry, configuration)
    }
    receipt = root / "receipt.json"
    value = json.loads(receipt.read_text())
    value["job_id"] = "91"
    receipt.write_text(json.dumps(value))
    before, after, accepted = (
        root / "runtime-inputs-before.json",
        root / "runtime-inputs-after.json",
        root / "runtime-inputs-acceptance.json",
    )
    for path in (before, after):
        path.write_text(json.dumps(files))
    accepted.write_text(
        json.dumps(
            {
                "passed": True,
                "unchanged": True,
                "job_id": "91",
                "files": files,
                "actual_imports": {
                    "entry": {"path": str(entry), "sha256": files[str(entry)]}
                },
            }
        )
    )
    row["verification"]["receipt"] = pin(receipt)
    row["verification"]["external_sources"] = {
        "receipt": pin(accepted),
        "before": pin(before),
        "after": pin(after),
        "files": [str(entry), str(configuration)],
    }
    return row


def test_original_external_sources_read_once_and_next_call_detects_changed_entry(
    tmp_path: Path,
) -> None:
    row = external_case(tmp_path)
    other = {**deepcopy(row), "id": "group.initialization"}
    original = deepcopy([row, other])
    report = verify_checkpoints([row, other], tmp_path, ENV)
    assert report["all_declared_conditions_matched"]
    assert report["body_reads"] == 9
    assert report["rows"][row["id"]]["external_source_file_count"] == 2
    assert report["runtime_or_resume_authority"] is False and [row, other] == original
    entry = tmp_path / "runtime/entry.py"
    entry.write_text("changed_entry = True\n")
    again = verify_checkpoints([row], tmp_path, ENV)
    assert again["rows"][row["id"]]["changed_conditions"] == [
        {"condition": "external_implementation", "input": str(entry)}
    ]


@pytest.mark.parametrize(
    "fault",
    [
        "job",
        "failed",
        "unstable",
        "after",
        "origin",
        "empty_origins",
        "uncovered",
        "foreign",
        "pin",
        "empty_files",
        "metadata_type",
        "alias",
    ],
)
def test_external_runtime_receipt_gap_never_silently_uses_core_inventory(
    tmp_path: Path, fault: str
) -> None:
    row = external_case(tmp_path)
    external = row["verification"]["external_sources"]
    selected = "receipt"
    path = Path(external[selected]["path"])
    value = json.loads(path.read_text())
    if fault == "job":
        value["job_id"] = "different-check"
    elif fault == "failed":
        value["passed"] = False
    elif fault == "unstable":
        value["unchanged"] = False
    elif fault == "after":
        selected = "after"
        path = Path(external[selected]["path"])
        value = json.loads(path.read_text())
        value[next(iter(value))] = "0" * 64
    elif fault == "origin":
        value["actual_imports"]["entry"]["sha256"] = "0" * 64
    elif fault == "empty_origins":
        value["actual_imports"] = {}
    elif fault == "uncovered":
        external["files"] = [str(tmp_path / "not-in-original-proof.py")]
    elif fault == "foreign":
        foreign = tmp_path / "foreign"
        foreign.mkdir()
        path = foreign / "runtime-inputs-acceptance.json"
    elif fault == "empty_files":
        external["files"] = []
    elif fault == "metadata_type":
        value = []
    elif fault == "alias":
        path = tmp_path / "alias.json"
        path.symlink_to("runtime-inputs-acceptance.json")
        external[selected] = pin(path)
    if fault != "alias":
        path.write_text(json.dumps(value))
        external[selected] = pin(path)
    if fault == "pin":
        path.write_text("{}")
    report = verify_checkpoints([row], tmp_path, ENV)
    assert report["rows"][row["id"]]["status"] == "unverified"
    assert not report["all_declared_conditions_matched"]


@pytest.mark.parametrize(
    "fault", ["none", "missing", "unknown_checkpoint", "unknown_input", "pin_type"]
)
def test_actual_cli_binds_selected_member_contract_and_refuses_missing_mapping(
    tmp_path: Path, fault: str
) -> None:
    row = external_case(tmp_path)
    receipt = tmp_path / "receipt.json"
    framework = json.loads(receipt.read_text())
    framework["environment_key"] = digest(environment_identity())
    receipt.write_text(json.dumps(framework))
    row["verification"]["receipt"] = pin(receipt)
    row.update(
        label="Original shared software",
        status="通过",
        execution_mode="复用",
        applicability={"assessment": "适用"},
        dependencies=[],
        evidence=[str(receipt)],
        reuse_conditions="Only exact immutable source and input facts",
        invalidation_conditions="Changed conditions",
        next_action="Only member binding and live gates",
        member_inputs_required=["contract"],
    )
    inputs = row["verification"]["inputs"][0]
    inputs["current"] = inputs["expected"]
    current: Any = pin(tmp_path / "new.json")
    if fault == "pin_type":
        current = "not-a-pin"
    selected = {"group.entry": {"contract": current}}
    if fault == "missing":
        selected = {}
    elif fault == "unknown_checkpoint":
        selected["group.other"] = {"contract": current}
    elif fault == "unknown_input":
        selected["group.entry"]["other"] = current
    block = {
        "observed_at": "explicit test premises",
        "common": [row],
        "members": {
            "new": {
                "historical": False,
                "condition_inputs": selected,
                "checkpoints": [],
            }
        },
    }
    original = deepcopy(block)
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps({"group_execution_plan": {"evidence_checkpoints": block}})
    )
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-P",
            str(W / "tools/development-checks/show-group-checkpoints.py"),
            "--plan",
            str(plan),
            "--member",
            "new",
            "--verify",
            "--json",
        ],
        capture_output=True,
        check=False,
        timeout=120,
        env=dict(os.environ),
    )
    if fault == "none":
        assert result.returncode == 0, result.stderr.decode()
        report = json.loads(result.stdout)
        checked = report["condition_verification"]["rows"]["group.entry"]
        assert (
            checked["status"] == "matched"
            and len(checked["member_parameter_checks"]) == 3
        )
        assert (
            report["recorded_rows"][0]["verification"]["inputs"][0]["current"]
            == current
        )
        assert (
            report["submission_delta"]["reuse"]
            and report["runtime_or_resume_authority"] is False
        )
    else:
        assert result.returncode != 0
        assert not result.stdout
    assert (
        json.loads(plan.read_text())["group_execution_plan"]["evidence_checkpoints"]
        == original
    )
