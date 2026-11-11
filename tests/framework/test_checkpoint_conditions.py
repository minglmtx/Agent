"""Original checkpoint condition comparison and the actual existing CLI.

Synthetic receipts exercise refusal boundaries. The final CLI case consumes an
actual passed receipt and real runtime inputs; no site/model/claim is invoked.
"""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest
from framework_checks.checkpoint_conditions import verify_checkpoints
from framework_checks.cache import digest
from framework_checks.environment import environment_identity

ENV = "1" * 64
W = Path("/anvme/workspace/r102bf10-lab-generate-skill")


def pin(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def sample(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    (root / "source").mkdir()
    source = root / "source/handler.py"
    source.write_text("original = True\n")
    receipt = root / "receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "schema_version": "framework-check/3",
                "passed": True,
                "source_stable_during_checks": True,
                "environment_key": ENV,
                "files": {
                    "handler.py": hashlib.sha256(source.read_bytes()).hexdigest()
                },
            }
        )
    )
    old: dict[str, Any] = {
        "task_id": "old",
        "goal": "old public goal",
        "schema_version": "navigation/1",
        "initialization": {"mode": "goto", "start": "/"},
        "recovery": {"component": "restore", "version": 1},
        "target": {"path": "/old"},
        "flag": True,
    }
    new = deepcopy(old)
    new.update(task_id="new", goal="new public goal")
    new["target"]["path"] = "/new"
    a, b = root / "old.json", root / "new.json"
    a.write_text(json.dumps(old))
    b.write_text(json.dumps(new))
    row: dict[str, Any] = {
        "id": "group.entry",
        "verification": {
            "receipt": pin(receipt),
            "source_root": str(root / "source"),
            "source_files": ["handler.py"],
            "minimum_scope": ["group.entry-consumer"],
            "inputs": [
                {
                    "name": "contract",
                    "expected": pin(a),
                    "current": pin(b),
                    "parameter_paths": ["/task_id", "/goal", "/target/path", "/flag"],
                }
            ],
        },
    }
    return row, old, new


def test_compatible_new_member_only_requires_parameter_binding_and_reads_each_body_once(
    tmp_path: Path,
) -> None:
    row, _, _ = sample(tmp_path)
    other = {**row, "id": "group.initializer"}
    original = deepcopy([row, other])
    report = verify_checkpoints([row, other], tmp_path, ENV)
    assert report["all_declared_conditions_matched"]
    assert report["body_reads"] == 4
    assert report["runtime_or_resume_authority"] is False
    assert len(report["rows"]["group.entry"]["member_parameter_checks"]) == 3
    assert [row, other] == original
    # A second invocation must independently reread, rather than inherit cache.
    (tmp_path / "source/handler.py").write_text("changed = True\n")
    again = verify_checkpoints([row], tmp_path, ENV)
    assert not again["all_declared_conditions_matched"]
    assert again["rows"]["group.entry"]["changed_conditions"] == [
        {"condition": "implementation", "input": "handler.py"}
    ]


@pytest.mark.parametrize(
    "fault",
    [
        "environment",
        "initializer",
        "recovery",
        "schema",
        "new_field",
        "parameter_type",
        "parameter_missing",
        "boolean_branch",
    ],
)
def test_exact_changes_name_only_the_affected_scope(tmp_path: Path, fault: str) -> None:
    row, _, new = sample(tmp_path)
    environment = ENV
    if fault == "environment":
        environment = "2" * 64
    elif fault == "initializer":
        new["initialization"]["mode"] = "special"
    elif fault == "recovery":
        new["recovery"]["component"] = "different-restore"
    elif fault == "schema":
        new["schema_version"] = "navigation/2"
        # A mistaken parameter allowlist must not hide a wire-version change.
        row["verification"]["inputs"][0]["parameter_paths"].append("/schema_version")
    elif fault == "new_field":
        new["special_state"] = {"required": True}
    elif fault == "parameter_type":
        new["target"]["path"] = 42
    elif fault == "parameter_missing":
        del new["goal"]
    else:
        new["flag"] = False
    path = tmp_path / "new.json"
    path.write_text(json.dumps(new))
    row["verification"]["inputs"][0]["current"] = pin(path)
    report = verify_checkpoints([row], tmp_path, environment)
    result = report["rows"][row["id"]]
    assert result["status"] == "changed" and result["changed_conditions"]
    assert result["minimum_scope"] == ["group.entry-consumer"]
    assert not report["all_declared_conditions_matched"]


@pytest.mark.parametrize(
    "fault",
    [
        "pin",
        "failed_receipt",
        "unstable_receipt",
        "uncovered_file",
        "receipt_files_type",
        "empty_scope",
        "alias",
        "unknown_pin_field",
        "missing_mapping",
        "duplicate_input",
        "empty_pointer",
        "duplicate_json",
        "nonfinite",
    ],
)
def test_missing_or_invalid_evidence_cannot_become_a_reuse_flag(
    tmp_path: Path, fault: str
) -> None:
    row, _, _ = sample(tmp_path)
    definition = row["verification"]
    if fault == "pin":
        (tmp_path / "old.json").write_text("{}")
    elif fault in (
        "failed_receipt",
        "unstable_receipt",
        "uncovered_file",
        "receipt_files_type",
    ):
        path = tmp_path / "receipt.json"
        value = json.loads(path.read_text())
        if fault == "failed_receipt":
            value["passed"] = False
        elif fault == "unstable_receipt":
            value["source_stable_during_checks"] = False
        elif fault == "receipt_files_type":
            value["files"] = []
        else:
            value["files"] = {}
        path.write_text(json.dumps(value))
        definition["receipt"] = pin(path)
    elif fault == "empty_scope":
        definition["source_files"] = []
    elif fault == "alias":
        path = tmp_path / "source/alias.py"
        path.symlink_to("handler.py")
        definition["source_files"] = ["alias.py"]
        value = json.loads((tmp_path / "receipt.json").read_text())
        value["files"]["alias.py"] = value["files"]["handler.py"]
        (tmp_path / "receipt.json").write_text(json.dumps(value))
        definition["receipt"] = pin(tmp_path / "receipt.json")
    elif fault == "unknown_pin_field":
        definition["inputs"][0]["expected"]["skip"] = True
    elif fault == "missing_mapping":
        del row["verification"]
    elif fault == "duplicate_input":
        definition["inputs"] *= 2
    elif fault == "empty_pointer":
        definition["inputs"][0]["parameter_paths"] = [""]
    else:
        path = tmp_path / "new.json"
        path.write_text(
            '{"goal":1,"goal":2}' if fault == "duplicate_json" else '{"value":NaN}'
        )
        definition["inputs"][0]["current"] = pin(path)
    report = verify_checkpoints([row], tmp_path, ENV)
    assert report["rows"][row["id"]]["status"] == "unverified"
    assert not report["all_declared_conditions_matched"]


def test_cached_body_does_not_bypass_complete_pin_validation(tmp_path: Path) -> None:
    row, _, _ = sample(tmp_path)
    other = deepcopy(row)
    other["id"] = "group.other"
    other["verification"]["inputs"][0]["expected"]["skip"] = True
    report = verify_checkpoints([row, other], tmp_path, ENV)
    assert report["rows"][row["id"]]["status"] == "matched"
    assert report["rows"][other["id"]]["status"] == "unverified"


def test_actual_checkpoint_cli_verifies_real_receipt_source_environment_and_runtime_input(
    tmp_path: Path,
) -> None:
    receipt = (
        W
        / "experiments/framework-combined-release-20261030-v1/source-consumption-check-4928944/result.json"
    )
    expected = json.loads(receipt.read_text())
    assert expected["passed"] and expected["environment_key"] == digest(
        environment_identity()
    )
    configuration = (
        W
        / "experiments/framework-admin-navigation-production-20261102-v1/runtime-source-consumption-candidate/entry-budgets.json"
    )
    row: dict[str, Any] = {
        "id": "group.entry",
        "label": "Exact scoped source/input comparison",
        "status": "通过",
        "execution_mode": "复用",
        "applicability": {"assessment": "适用"},
        "dependencies": [],
        "evidence": [str(receipt)],
        "reuse_conditions": "Exact declared inputs",
        "invalidation_conditions": "Changed inputs",
        "next_action": "Reuse unchanged conditions",
        "verification": {
            "receipt": pin(receipt),
            "source_root": str(
                W / "code/lab-generate-skill-source-consumption-candidate-20261105"
            ),
            "source_files": ["src/lab_generate_skill/policies/publication_inputs.py"],
            "minimum_scope": ["group.entry"],
            "inputs": [
                {
                    "name": "configuration",
                    "expected": pin(configuration),
                    "current": pin(configuration),
                    "parameter_paths": [],
                }
            ],
        },
    }
    assert tmp_path.is_relative_to(W)
    path = tmp_path / "plan.json"
    path.write_text(
        json.dumps(
            {
                "group_execution_plan": {
                    "evidence_checkpoints": {
                        "observed_at": "test current conditions",
                        "common": [row],
                        "members": {},
                    }
                }
            }
        )
    )
    command = [
        sys.executable,
        "-B",
        "-P",
        str(W / "tools/development-checks/show-group-checkpoints.py"),
        "--plan",
        str(path),
        "--verify",
        "--json",
    ]
    result = subprocess.run(
        command, capture_output=True, check=False, timeout=120, env=dict(os.environ)
    )
    assert result.returncode == 0, result.stderr.decode()
    report = json.loads(result.stdout)
    assert report["condition_verification"]["all_declared_conditions_matched"]
    assert report["submission_delta"]["reuse"][0]["checkpoint"] == "group.entry"
    # Matched accepted conditions cannot qualify an unfinished common stage.
    pending = {
        **row,
        "id": "group.install",
        "status": "未开始",
        "execution_mode": "待核",
        "evidence": [],
        "next_action": "Only finish the missing exact installation",
    }
    path.write_text(
        json.dumps(
            {
                "group_execution_plan": {
                    "evidence_checkpoints": {
                        "observed_at": "test pending common stage",
                        "common": [row, pending],
                        "members": {},
                    }
                }
            }
        )
    )
    result = subprocess.run(
        command, capture_output=True, check=False, timeout=120, env=dict(os.environ)
    )
    assert result.returncode == 2, result.stderr.decode()
    report = json.loads(result.stdout)
    assert (
        report["condition_verification"]["rows"]["group.install"]["status"]
        == "unverified"
    )
    assert not report["condition_verification"]["all_declared_conditions_matched"]
    # An actual changed current configuration is rejected; no source/Actor acts.
    changed = tmp_path / "changed-config.json"
    value = json.loads(configuration.read_text())
    value["task_seconds"] += 1
    changed.write_text(json.dumps(value))
    row["verification"]["inputs"][0]["current"] = pin(changed)
    path.write_text(
        json.dumps(
            {
                "group_execution_plan": {
                    "evidence_checkpoints": {
                        "observed_at": "test current conditions",
                        "common": [row],
                        "members": {},
                    }
                }
            }
        )
    )
    result = subprocess.run(
        command, capture_output=True, check=False, timeout=120, env=dict(os.environ)
    )
    assert result.returncode == 2, result.stderr.decode()
    report = json.loads(result.stdout)
    assert report["submission_delta"]["supplement"][0]["checkpoint"] == "group.entry"
    assert (
        json.loads(path.read_text())["group_execution_plan"]["evidence_checkpoints"][
            "common"
        ][0]["status"]
        == "通过"
    )
