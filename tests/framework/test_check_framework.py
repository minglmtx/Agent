"""Check orchestration must not turn a module selection into a full regression.

Child commands are recorded stubs: these are runner behavior tests, not another
nested software run. One real Slurm selected-mode invocation verifies delivery.
"""

import importlib.util
import json
from pathlib import Path
import subprocess
import tomllib
from types import ModuleType
import pytest


def setup_driver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
    *,
    failed: bool = False,
    timeout: bool = False,
    fake_inventory: bool = True,
) -> tuple[ModuleType, list[list[str]]]:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    path = Path(__file__).resolve().parents[2] / "tools" / "check_framework.py"
    spec = importlib.util.spec_from_file_location("framework_driver_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "environment_identity", lambda: {"runtime": "unit"})
    monkeypatch.setattr(module, "WORKSPACE", tmp_path)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    if fake_inventory:
        monkeypatch.setattr(module, "inventory", lambda: {"src/fixture.py": "a" * 64})
    monkeypatch.setenv("SLURM_JOB_ID", "unit-check")
    monkeypatch.setattr(
        module.sys,
        "argv",
        [str(path), "--output", str(tmp_path / "result"), *arguments],
    )
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if "pytest" in command and timeout:
            raise subprocess.TimeoutExpired(command, 300)
        if "black" in command or "mypy" in command:
            (
                tmp_path
                / "result"
                / ("type_check.log" if "mypy" in command else "format_check.log")
            ).write_text("unit log")
        return subprocess.CompletedProcess[str](
            command, 1 if failed and "pytest" in command else 0
        )

    monkeypatch.setattr(module.subprocess, "run", run)
    return module, calls


def read_result(tmp_path: Path) -> dict[str, object]:
    result: dict[str, object] = json.loads(
        (tmp_path / "result" / "result.json").read_text()
    )
    return result


def test_default_selected_module_and_affected_caller_run_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = [
        "tests/framework/test_one.py",
        "tests/framework/test_caller.py::test_interface",
    ]
    driver, calls = setup_driver(
        tmp_path,
        monkeypatch,
        ["--test-first", selected[0], "--test-first", selected[1]],
    )
    assert driver.main() == 0
    tests = [c for c in calls if "pytest" in c]
    assert len(tests) == 1 and tests[0][4:6] == selected
    assert all("tests/framework" not in c for c in calls)
    value = read_result(tmp_path)
    assert value["schema_version"] == "framework-check/3"
    assert value["test_scope"] == {
        "mode": "selected",
        "selected": selected,
        "full_regression_run": False,
    }
    assert value["passed"] is True
    assert value["selected_test_budget_seconds"] == 300


@pytest.mark.parametrize("budget", [300, 420, 600, 3600])
def test_explicit_selected_budget_reaches_subprocess_and_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, budget: int
) -> None:
    driver, calls = setup_driver(
        tmp_path,
        monkeypatch,
        [
            "--test-first",
            "tests/framework/test_chain.py",
            "--selected-test-budget-seconds",
            str(budget),
        ],
    )
    original = driver.subprocess.run
    observed: list[object] = []

    def run(command: list[str], **kwargs: object) -> object:
        if "pytest" in command:
            observed.append(kwargs["timeout"])
        return original(command, **kwargs)

    monkeypatch.setattr(driver.subprocess, "run", run)
    assert driver.main() == 0 and observed == [budget]
    result = read_result(tmp_path)
    assert result["selected_test_budget_seconds"] == budget
    checks = result["checks"]
    assert isinstance(checks, list)
    assert [c["timeout_seconds"] for c in checks if c["name"] == "selected_tests"] == [
        budget
    ]
    assert len([c for c in calls if "pytest" in c]) == 1


@pytest.mark.parametrize("value", ["0", "-1", "301", "421", "601", "inf", "1.5"])
def test_invalid_selected_budget_has_no_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    driver, calls = setup_driver(
        tmp_path,
        monkeypatch,
        [
            "--test-first",
            "tests/framework/test_chain.py",
            "--selected-test-budget-seconds",
            value,
        ],
    )
    with pytest.raises(SystemExit) as error:
        driver.main()
    assert error.value.code == 2 and not calls and not (tmp_path / "result").exists()


def test_selected_budget_does_not_change_overall_suite_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver, calls = setup_driver(
        tmp_path,
        monkeypatch,
        ["--full-regression", "--selected-test-budget-seconds", "420"],
    )
    with pytest.raises(SystemExit):
        driver.main()
    assert not calls


@pytest.mark.parametrize("selected", [False, True])
def test_overall_suite_requires_explicit_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, selected: bool
) -> None:
    args = ["--full-regression"]
    if selected:
        args += ["--test-first", "tests/framework/test_failed.py::test_case"]
    driver, calls = setup_driver(tmp_path, monkeypatch, args)
    assert driver.main() == 0
    tests = [c for c in calls if "pytest" in c]
    assert len(tests) == (2 if selected else 1) and tests[-1][4] == "tests/framework"
    value = read_result(tmp_path)
    assert value["test_scope"] == {
        "mode": "full_regression",
        "selected": ["tests/framework/test_failed.py::test_case"] if selected else [],
        "full_regression_run": True,
    }


def test_no_selection_does_not_silently_run_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver, calls = setup_driver(tmp_path, monkeypatch, [])
    with pytest.raises(SystemExit) as error:
        driver.main()
    assert error.value.code == 2 and calls == []
    assert not (tmp_path / "result").exists()


@pytest.mark.parametrize("timeout", [False, True])
def test_failed_selected_check_stays_failed_without_widening_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, timeout: bool
) -> None:
    driver, calls = setup_driver(
        tmp_path,
        monkeypatch,
        ["--test-first", "tests/framework/test_one.py"],
        failed=True,
        timeout=timeout,
    )
    assert driver.main() == 1
    assert len([c for c in calls if "pytest" in c]) == 1
    value = read_result(tmp_path)
    assert value["passed"] is False
    assert value["test_scope"] == {
        "mode": "selected",
        "selected": ["tests/framework/test_one.py"],
        "full_regression_run": False,
    }


def test_existing_receipt_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver, calls = setup_driver(
        tmp_path, monkeypatch, ["--test-first", "tests/framework/test_one.py"]
    )
    (tmp_path / "result").mkdir()
    path = tmp_path / "result" / "result.json"
    path.write_text("original")
    with pytest.raises(SystemExit):
        driver.main()
    assert calls == [] and path.read_text() == "original"


def test_selected_checks_still_require_compute_allocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver, calls = setup_driver(
        tmp_path, monkeypatch, ["--test-first", "tests/framework/test_one.py"]
    )
    monkeypatch.delenv("SLURM_JOB_ID")
    with pytest.raises(SystemExit):
        driver.main()
    assert calls == []


def test_every_checked_source_layer_is_explicitly_type_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver, _ = setup_driver(tmp_path, monkeypatch, [])
    project = Path(__file__).resolve().parents[2]
    config = tomllib.loads((project / "pyproject.toml").read_text())
    configured = set(config["tool"]["mypy"]["files"])
    source_layers = {scope for scope in driver.SCOPES if scope.startswith("src/")}
    assert "src/lab_generate_skill/teacher" in source_layers
    assert source_layers <= configured, source_layers - configured


@pytest.mark.parametrize("change", ["content", "add", "remove", "empty"])
def test_recorded_fixture_changes_invalidate_pass_reuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    from framework_checks.cache import file_digest
    from framework_checks.selection import previously_passed

    driver, calls = setup_driver(
        tmp_path,
        monkeypatch,
        ["--test-first", "tests/framework/test_one.py::test_case"],
        fake_inventory=False,
    )
    monkeypatch.setattr(driver, "SCOPES", ("src",))
    for name in [
        "pyproject.toml",
        ".gitignore",
        "cluster/freeze-framework-artifact.sbatch",
        "src/fixture.py",
    ]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
    fixture = tmp_path / "tests/framework/fixtures/recorded/reply.json"
    fixture.parent.mkdir(parents=True)
    fixture.write_text('{"value":1}')
    before = driver.inventory()
    assert before["tests/framework/fixtures/recorded/reply.json"] == file_digest(
        fixture
    )
    assert driver.main() == 0
    recorded = json.loads((tmp_path / "result/result.json").read_bytes())
    assert recorded["files"] == before
    black = next(c for c in calls if "black" in c)
    assert "tests/framework/fixtures/recorded/reply.json" not in black
    cases = tmp_path / "selected-cases.json"
    cases.write_text(
        json.dumps(
            {
                "schema_version": "check-cases/1",
                "exitstatus": 0,
                "passed": ["tests/framework/test_one.py::test_case"],
            }
        )
    )
    receipt = tmp_path / "accepted.json"
    receipt.write_text(
        json.dumps(
            {
                "schema_version": "framework-check/3",
                "passed": True,
                "source_stable_during_checks": True,
                "files": before,
                "environment_key": "unit",
                "selected_cases_sha256": file_digest(cases),
            }
        )
    )
    assert previously_passed([receipt], driver.inventory(), "unit")[0] == [
        "tests/framework/test_one.py::test_case"
    ]
    if change == "content":
        fixture.write_text('{"value":2}')
    elif change == "add":
        (fixture.parent / "new.txt").write_text("new")
    elif change == "remove":
        fixture.unlink()
    else:
        fixture.write_bytes(b"")
    with pytest.raises(ValueError, match="identical successful"):
        previously_passed([receipt], driver.inventory(), "unit")
