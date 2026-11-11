"""Only N project/runtime bindings change in the accepted single-member entry."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
P = W / "experiments/framework-combined-release-20261030-v1"
AP = W / "experiments/framework-admin-navigation-production-20261102-v1"
MP = W / "experiments/framework-map-navigation42-production-20261102-v1"
N = W / "code/lab-generate-skill-next-candidate-20261104"
RUNTIME = AP / "runtime-next-candidate"
NAMES = (
    "admin_production_entry.py",
    "admin_production_supply.py",
    "admin_production_deployment.py",
    "admin_production_installation.py",
    "admin_production_member.py",
    "production-budget.sbatch",
    "entry-budgets.json",
    "job-budgets.json",
    "source-recovery-budgets.json",
)


def test_exact_next_outer_types_and_pins(tmp_path: Path) -> None:
    accepted = json.loads((P / "runtime-inputs-4913322-after.json").read_bytes())
    paths = [RUNTIME / name for name in NAMES]
    paths += [
        P / "prepare_next_runtime_software.py",
        P / "install-next-admin-runtime.sbatch",
    ]
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    for name in NAMES:
        old = AP / "runtime-candidate" / name
        raw = old.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == accepted[str(old)]
        expected = raw.replace(
            b"lab-generate-skill-integration-candidate-20261103",
            b"lab-generate-skill-next-candidate-20261104",
        ).replace(b"runtime-candidate", b"runtime-next-candidate")
        assert (RUNTIME / name).read_bytes() == expected
    output = P / ("next-runtime-inputs-" + os.environ["SLURM_JOB_ID"] + "-before.json")
    output.write_text(json.dumps(before, sort_keys=True, indent=2) + "\n")
    env = {
        **os.environ,
        "PYTHONPATH": f"{RUNTIME}:{AP}:{MP}:{N / 'tools'}:{N / 'src'}:{N / 'tests/framework'}:{W / 'tools/development-checks/mypy-1.15.0'}",
        "MYPYPATH": f"{RUNTIME}:{AP}:{MP}",
    }
    checked = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "mypy",
            "--config-file",
            str(N / "pyproject.toml"),
            "--cache-dir",
            str(tmp_path / "mypy"),
            "--follow-imports=silent",
            "--ignore-missing-imports",
            *(str(p) for p in paths if p.suffix == ".py"),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
        check=False,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr
    for shell in (
        RUNTIME / "production-budget.sbatch",
        P / "install-next-admin-runtime.sbatch",
    ):
        subprocess.run(["/usr/bin/bash", "-n", str(shell)], check=True, timeout=10)
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    output.with_name(output.name.replace("-before", "-after")).write_text(
        json.dumps(after, sort_keys=True, indent=2) + "\n"
    )
    assert after == before
