"""Run the implemented framework gates on Slurm, recording commands and hashes.

Input: --output for a new workspace report directory; optional --format to
format development files first; repeated --test-first NODE selects changed
modules, affected callers or failed cases. Only explicit --full-regression adds
the complete framework suite for overall integration. Output: command logs, XML and
result.json. Nonzero checks stay visible; no test result is treated as a
deployment/experiment receipt. Never run this on a login node.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from framework_checks.cache import digest, file_digest
from framework_checks.environment import environment_identity
from framework_checks.static import static_checks
from framework_checks.selection import previously_passed

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
SCOPES = (
    "src/lab_generate_skill/domain",
    "src/lab_generate_skill/policies",
    "src/lab_generate_skill/ports",
    "src/lab_generate_skill/adapters",
    "src/lab_generate_skill/runtime",
    "src/lab_generate_skill/application",
    "src/lab_generate_skill/registry",
    "src/lab_generate_skill/release",
    "src/lab_generate_skill/generator",
    "src/lab_generate_skill/actor",
    "src/lab_generate_skill/teacher",
    "src/lab_generate_skill/bootstrap",
    "src/lab_generate_skill/sites",
    "src/lab_generate_skill/task_families",
    "src/lab_generate_skill/evaluators",
    "tests/framework",
    "tools/check_framework.py",
    "tools/framework_checks",
    "tools/read_historical_reference.py",
)


def inventory() -> dict[str, str]:
    paths = [ROOT / "pyproject.toml", ROOT / ".gitignore"]
    paths.extend(sorted((ROOT / "cluster").glob("check*.sbatch")))
    paths.append(ROOT / "cluster" / "freeze-framework-artifact.sbatch")
    for scope in SCOPES:
        path = ROOT / scope
        paths.extend(sorted(path.rglob("*.py")) if path.is_dir() else [path])
    paths.extend(sorted((ROOT / "src").rglob("*.py")))
    # Recorded JSON/text/binary fixtures affect behavioral evidence even though
    # Black/Mypy only consume Python. Add/remove/content changes invalidate reuse.
    paths.extend(
        sorted(
            path
            for path in (ROOT / "tests/framework/fixtures").rglob("*")
            if path.is_file()
        )
    )
    paths.extend(sorted((ROOT / "tests").glob("conftest.py")))
    paths.extend(sorted(ROOT.glob("conftest.py")))
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--format", action="store_true")
    parser.add_argument("--test-first", action="append", default=[], metavar="NODE")
    parser.add_argument(
        "--selected-test-budget-seconds",
        type=int,
        choices=(300, 420, 600, 3600, 14400),
        default=300,
        help="Explicit selected integration budget; default300 unchanged, recorded in each receipt",
    )
    parser.add_argument(
        "--full-regression",
        action="store_true",
        help="Explicit overall-integration gate; never implied by module checks",
    )
    parser.add_argument(
        "--fresh-static",
        action="store_true",
        help="Execute static gates even when identical evidence exists",
    )
    parser.add_argument(
        "--exclude-passed-from",
        action="append",
        type=Path,
        default=[],
        metavar="RESULT",
    )
    args = parser.parse_args()
    if args.selected_test_budget_seconds != 300 and not args.test_first:
        parser.error("An explicit selected integration budget requires --test-first")
    if args.full_regression and args.exclude_passed_from:
        parser.error("The overall gate cannot exclude previously passed cases")
    if not args.test_first and not args.full_regression:
        parser.error(
            "Select module/caller tests with --test-first; use --full-regression only for the overall gate"
        )
    if not os.environ.get("SLURM_JOB_ID"):
        parser.error("Framework checks require a Slurm compute allocation")
    output = args.output.resolve()
    if not output.is_relative_to(WORKSPACE) or output == WORKSPACE:
        parser.error("Check outputs must stay inside the project workspace")
    output.mkdir(parents=True, exist_ok=True)
    if (output / "result.json").exists():
        parser.error("Keep prior results; use a fresh output directory")
    checks: list[dict[str, object]] = []

    def run(name: str, arguments: list[str], *, timeout_seconds: int = 300) -> int:
        command = [sys.executable, "-B", "-m", *arguments]
        started = time.monotonic()
        with (output / f"{name}.log").open("w") as log:
            try:
                completed = subprocess.run(
                    command,
                    cwd=ROOT,
                    env=(
                        {
                            **os.environ,
                            "LAB_CHECK_CASES_PATH": str(output / "selected-cases.json"),
                        }
                        if name == "selected_tests"
                        else dict(os.environ)
                    ),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=timeout_seconds,
                    check=False,
                )
                code = completed.returncode
            except subprocess.TimeoutExpired:
                code = 124
                log.write(f"\nCheck exceeded its {timeout_seconds}-second deadline.\n")
        checks.append(
            {
                "name": name,
                "execution": "executed",
                "command": command,
                "returncode": code,
                "elapsed_seconds": time.monotonic() - started,
                "timeout_seconds": timeout_seconds,
            }
        )
        return code

    # Explicit source files prevent asset-oriented .gitignore directory rules
    # from silently excluding a newly implemented Python package from Black.
    format_sources = [
        path
        for path in inventory()
        if path.endswith(".py")
        and any(path == scope or path.startswith(scope + "/") for scope in SCOPES)
    ]
    formatting = run("format_apply", ["black", *format_sources]) if args.format else 0
    before = inventory()
    environment = environment_identity()
    environment_key = digest(environment)
    excluded, reused_tests = previously_passed(
        args.exclude_passed_from, before, environment_key
    )
    static_checks(
        cache=WORKSPACE / "cache/framework-checks/v1",
        output=output,
        files=before,
        format_sources=format_sources,
        environment=environment,
        run=run,
        checks=checks,
        current_files=inventory,
        fresh=args.fresh_static or args.full_regression,
    )
    if args.test_first:
        run(
            "selected_tests",
            [
                "pytest",
                *args.test_first,
                *[f"--deselect={node}" for node in excluded],
                "-p",
                "framework_checks.pytest_reports",
                "-q",
                "-o",
                f"cache_dir={output / 'pytest-cache'}",
                f"--junitxml={output / 'selected-tests.xml'}",
            ],
            timeout_seconds=args.selected_test_budget_seconds,
        )
    if args.full_regression:
        run(
            "tests",
            [
                "pytest",
                "tests/framework",
                "-q",
                "-o",
                f"cache_dir={output / 'pytest-cache'}",
                f"--junitxml={output / 'pytest.xml'}",
            ],
            # Whole-suite wall time includes startup/reporting; runtime and
            # individual test deadlines are unchanged.
            timeout_seconds=600,
        )
    after = inventory()
    passed = (
        formatting == 0
        and all(item["returncode"] == 0 for item in checks)
        and before == after
    )
    result = {
        "schema_version": "framework-check/3",
        "environment_key": environment_key,
        "selected_cases_sha256": (
            file_digest(output / "selected-cases.json")
            if (output / "selected-cases.json").exists()
            else None
        ),
        "excluded_passed_nodes": excluded,
        "reused_test_evidence": reused_tests,
        "passed": passed,
        "job_id": os.environ["SLURM_JOB_ID"],
        "python": sys.executable,
        "checks": checks,
        "files": after,
        "source_stable_during_checks": before == after,
        "scope": list(SCOPES),
        "test_scope": {
            "mode": "full_regression" if args.full_regression else "selected",
            "selected": args.test_first,
            "full_regression_run": args.full_regression,
        },
        "formal_experiments_run": False,
        "framework_complete": False,
        "selected_test_budget_seconds": args.selected_test_budget_seconds,
    }
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": passed, "result": str(output / "result.json")}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
