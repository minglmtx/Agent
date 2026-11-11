"""Thin original entry selectors: frozen inputs, profile and no old fallback.

Only extracted stdlib preflight runs against explicit synthetic declarations.
No launcher/site/model/claim is invoked; a descriptor is never execution rights.
"""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
P = W / "experiments/framework-combined-release-20261030-v1"


def wrapper(is_map: bool) -> Path:
    package = (
        "framework-map-navigation42-production-20261102-v1"
        if is_map
        else "framework-admin-navigation-production-20261102-v1"
    )
    return W / "experiments" / package / "runtime-candidate/production-budget.sbatch"


def select(
    root: Path, is_map: bool, partition: str, paths: tuple[Path, Path]
) -> subprocess.CompletedProcess[str]:
    script = (
        wrapper(is_map)
        .read_text()
        .split("<<'PYSELECT'\n", 1)[1]
        .split("\nPYSELECT\n", 1)[0]
    )
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            script,
            str(root),
            str(root / "runtime-candidate"),
            partition,
            "map_navigation42" if is_map else "admin_navigation71",
            *map(str, paths),
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def fixture(root: Path, is_map: bool) -> tuple[tuple[Path, Path], dict[str, Any], Path]:
    runtime = root / "runtime-candidate"
    runtime.mkdir(parents=True)
    names = [
        "production_entry.py" if is_map else "admin_production_entry.py",
        "production-budget.sbatch",
        "entry-budgets.json",
        "job-budgets.json",
        "source-recovery-budgets.json",
    ]
    pins = {}
    for name in names:
        p = runtime / name
        p.write_bytes(b"explicit unit preflight bytes")
        pins[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    directory = root / "software"
    directory.mkdir()
    raw = (json.dumps(pins, sort_keys=True) + "\n").encode()
    (directory / "runtime-entry-inputs.json").write_bytes(raw)
    software = {
        "passed": True,
        "runtime_entry": {
            "schema_version": "runtime-entry-preparation/1",
            "consumer": "map_navigation42" if is_map else "admin_navigation71",
            "actual_source_or_training_grant": False,
            "outer_inputs_sha256": hashlib.sha256(raw).hexdigest(),
        },
    }
    receipt = directory / "software.json"
    receipt.write_text(json.dumps(software))
    paths = []
    for index, gpu in enumerate(("a100_40gb", "a40")):
        p = root / f"deployment-{index}.json"
        p.write_text(
            json.dumps(
                {
                    "passed": True,
                    "formal_training_qualification": False,
                    "config": {"long_context": {"gpu_class": gpu}},
                    "software_path": str(receipt),
                }
            )
        )
        paths.append(p)
    return (paths[0], paths[1]), software, receipt


@pytest.mark.parametrize("is_map", [True, False])
@pytest.mark.parametrize("partition,index", [("a100", 0), ("a40", 1)])
def test_exact_prepared_inputs_select_only_compatible_immutable_deployment(
    tmp_path: Path, is_map: bool, partition: str, index: int
) -> None:
    paths, _, _ = fixture(tmp_path, is_map)
    before = [p.read_bytes() for p in paths]
    for _ in range(2):
        result = select(tmp_path, is_map, partition, paths)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(paths[index])
    assert before == [p.read_bytes() for p in paths]


@pytest.mark.parametrize("is_map", [True, False])
@pytest.mark.parametrize(
    "fault",
    [
        "partition",
        "same",
        "old",
        "wrong_consumer",
        "grant",
        "manifest_digest",
        "changed_input",
        "missing_required",
        "wrong_gpu",
        "outside",
        "relative",
    ],
)
def test_invalid_profile_or_input_refuses_before_original_entry(
    tmp_path: Path, is_map: bool, fault: str
) -> None:
    paths, software, receipt = fixture(tmp_path, is_map)
    partition = "a40"
    if fault == "partition":
        partition = "rtxpro6k"
    elif fault == "same":
        paths = (paths[0], paths[0])
    elif fault == "old":
        del software["runtime_entry"]
    elif fault == "wrong_consumer":
        software["runtime_entry"]["consumer"] = "foreign"
    elif fault == "grant":
        software["runtime_entry"]["actual_source_or_training_grant"] = True
    elif fault == "manifest_digest":
        software["runtime_entry"]["outer_inputs_sha256"] = "0" * 64
    elif fault == "changed_input":
        (tmp_path / "runtime-candidate/job-budgets.json").write_text("changed")
    elif fault == "missing_required":
        path = receipt.parent / "runtime-entry-inputs.json"
        pins = json.loads(path.read_bytes())
        del pins[str(tmp_path / "runtime-candidate/job-budgets.json")]
        raw = json.dumps(pins).encode()
        path.write_bytes(raw)
        software["runtime_entry"]["outer_inputs_sha256"] = hashlib.sha256(
            raw
        ).hexdigest()
    elif fault == "wrong_gpu":
        value = json.loads(paths[1].read_bytes())
        value["config"]["long_context"]["gpu_class"] = "a100_40gb"
        paths[1].write_text(json.dumps(value))
    elif fault == "outside":
        paths = (paths[0], tmp_path.parent / "missing-outside.json")
    elif fault == "relative":
        paths = (paths[0], Path("relative.json"))
    receipt.write_text(json.dumps(software))
    result = select(tmp_path, is_map, partition, paths)
    assert result.returncode != 0 and not result.stdout


def test_actual_wrapper_syntax_single_member_and_fixed_budget_limits() -> None:
    for is_map in (True, False):
        path = wrapper(is_map)
        text = path.read_text()
        result = subprocess.run(
            ["/bin/bash", "-n", str(path)], capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0, result.stderr
        assert "#SBATCH --time=" + ("05:00:00" if is_map else "04:00:00") in text
        assert "#SBATCH --signal=B:USR1@4800" in text
        assert "[[ $# == 3 ]] || exit 64" in text
        assert "black " not in text and "mypy " not in text
        assert 'kill -USR1 "$production_controller_pid"' in text
    for name in ("check-runtime-entries.sbatch", "install-runtime-candidates.sbatch"):
        result = subprocess.run(
            ["/bin/bash", "-n", str(P / name)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
