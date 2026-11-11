"""Exact isolated outer consumers compile; original unit routing checks the cap.

No source/model claim is dispatched. Installed/deployed runtime is a separate
exit; these checks are only used with the explicit repair runtime search path.
"""

from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
import pytest

import admin_production_member as member_module
import production_task_plan as map_plan
import admin_production_task_plan as admin_plan
from lab_generate_skill.domain.operation_window import OperationTimeWindow
from lab_generate_skill.runtime.bounded_lifecycle import BoundedOperationControls
from test_admin_production_member import routing as routing
from test_admin_production_admission import case as case
from test_admin_navigation_input import contracts as contracts
from site_instance_fixtures import node_path as node_path

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
MP = W / "experiments/framework-map-navigation42-production-20261102-v1"
AP = W / "experiments/framework-admin-navigation-production-20261102-v1"
O = W / "code/lab-generate-skill-group-owner-candidate-20261104"
PATHS = (
    MP / "runtime-repair-candidate/production_entry.py",
    MP / "runtime-repair-candidate/production_task_plan.py",
    AP / "runtime-repair-candidate/admin_production_entry.py",
    AP / "runtime-repair-candidate/admin_production_member.py",
    AP / "runtime-repair-candidate/admin_production_task_plan.py",
    AP / "runtime-repair-candidate/admin_production_supply.py",
    AP / "runtime-repair-candidate/admin_production_deployment.py",
    AP / "runtime-repair-candidate/admin_production_installation.py",
    MP / "runtime-repair-candidate/deployment_preflight.py",
    W
    / "experiments/framework-combined-release-20261030-v1/prepare_repair_runtime_software.py",
    W / "experiments/framework-combined-release-20261030-v1/readback-repair-runtime.py",
)


def test_exact_repaired_outer_consumers_are_typed(tmp_path: Path) -> None:
    assert Path(member_module.__file__) == PATHS[3]
    assert Path(map_plan.__file__) == PATHS[1]
    assert Path(admin_plan.__file__) == PATHS[4]
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in PATHS}
    compiled = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "mypy",
            "--config-file",
            str(O / "pyproject.toml"),
            "--cache-dir",
            str(tmp_path / "mypy"),
            "--follow-imports=silent",
            "--ignore-missing-imports",
            *(str(p) for p in PATHS),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "repaired-outer-types.log"
    ).write_text(compiled.stdout + compiled.stderr)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    assert before == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in PATHS}
    (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "repaired-outer-inputs.json"
    ).write_text(json.dumps(before, indent=2) + "\n")


def test_admin_model_ready_handoff_uses_original_controller_and_preserves_close(
    routing: Any,
) -> None:
    args, events, _, expected, c = routing
    clock = args["clock"]
    now = clock.utcnow()
    controls = BoundedOperationControls(
        args["controls"],
        clock,
        OperationTimeWindow(
            owner=args["model"].token.owner,
            execution_deadline=now + timedelta(seconds=120),
            cleanup_deadline=now + timedelta(seconds=300),
            hard_end=now + timedelta(seconds=360),
        ),
    )
    prebound = controls.bind(args["model_operation"])
    args.update(controls=controls, task_seconds=20)
    result = member_module.execute_claimed_admin_member(**args)
    assert result.result is expected
    assert 0 < prebound.checkpoint() <= 20
    assert 0 < result.phase_seconds["task_seconds_at_handoff"] <= 20
    assert (
        events.index("model-bind")
        < events.index("site-bind")
        < events.index("execute")
        < events.index("model-close")
    )
    assert c.owned.resources.site.phase == "new"


def test_admin_insufficient_task_window_closes_model_before_site_dispatch(
    routing: Any,
) -> None:
    args, events, _, _, _ = routing
    clock = args["clock"]
    now = clock.utcnow()
    controls = BoundedOperationControls(
        args["controls"],
        clock,
        OperationTimeWindow(
            owner=args["model"].token.owner,
            execution_deadline=now + timedelta(seconds=10),
            cleanup_deadline=now + timedelta(seconds=300),
            hard_end=now + timedelta(seconds=360),
        ),
    )
    args.update(controls=controls, task_seconds=20)
    with pytest.raises(ValueError, match="Insufficient"):
        member_module.execute_claimed_admin_member(**args)
    assert (
        events[-1] == "model-close"
        and "site-bind" not in events
        and "execute" not in events
    )
