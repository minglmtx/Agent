"""New outer entry budgets before effects; no site/model/claim permissions.

Separate Python import graphs preserve the real canonical Admin dataclass and
supplier identities while original pending outer modules remain unchanged.
"""

from pathlib import Path
from datetime import datetime, timedelta, timezone
import os
import subprocess
import sys

import pytest
from lab_generate_skill.domain.operation_window import OperationWindowBudgets
from lab_generate_skill.domain.source_recovery_budget import SourceRecoveryBudgets
from lab_generate_skill.domain.lifecycle import ResourceOwner
from test_lifecycle import ManualClock
from production_task_plan import MapProductionBudgets
from admin_production_task_plan import AdminProductionBudgets
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.domain.operation_window import OperationTimeWindow
from lab_generate_skill.runtime.bounded_lifecycle import BoundedOperationControls
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_lifecycle import CancelSwitch
from test_run_journal import command
from trace_journal_fixtures import fixture as trace_fixture

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
I = W / "code/lab-generate-skill-integration-candidate-20261103"
MP = W / "experiments/framework-map-navigation42-production-20261102-v1"
AP = W / "experiments/framework-admin-navigation-production-20261102-v1"


def run_child(program: str, *, timeout: int = 45) -> subprocess.CompletedProcess[str]:
    paths = [
        AP / "runtime-candidate",
        MP / "runtime-candidate",
        AP,
        MP,
        I / "tools",
        I / "src",
        I / "tests/framework",
        W / "tools/development-checks/mypy-1.15.0",
    ]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(map(str, paths))
    environment["MYPYPATH"] = os.pathsep.join(map(str, paths[:7]))
    return subprocess.run(
        [sys.executable, "-B", "-c", program],
        env=environment,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


PRELUDE = """
from pathlib import Path
from contextlib import contextmanager
from types import SimpleNamespace
import os
from lab_generate_skill.domain.operation_window import OperationWindowBudgets
from lab_generate_skill.domain.source_recovery_budget import SourceRecoveryBudgets
from admin_production_task_plan import AdminProductionBudgets
job=OperationWindowBudgets(execution_seconds=21600,cleanup_seconds=7200,final_margin_seconds=600,stop_signal_lead_seconds=7800)
recovery=SourceRecoveryBudgets(preparation_metadata_seconds=300,browser_close_seconds=1200,restore_seconds=600,resume_seconds=300,reset_facts_seconds=600,site_close_seconds=600)
entry=AdminProductionBudgets.model_validate(AdminProductionBudgets().model_dump())
"""


@pytest.mark.parametrize(
    "variant",
    [
        "complete",
        "implicit_defaults",
        "root_mismatch",
        "bad_recovery",
        "insufficient_recovery_reserve",
    ],
)
def test_admin_real_entry_consumes_explicit_budget_before_original_supplier(
    variant: str,
) -> None:
    program = PRELUDE + """
import admin_production_entry as entry_module
import admin_production_inputs as inputs
import admin_production_deployment as deployment
import admin_production_supply as supplier
calls=[]
selected=SimpleNamespace(private=SimpleNamespace(task=SimpleNamespace(source_task_id="original")))
def group(control):
    calls.append("group")
    return (selected,)
def load(path,budget,control):
    assert budget==entry
    calls.append("deployment")
    return "original-installed-declaration"
@contextmanager
def supply(member,installed,budget,origin,actions,output,*,job_budgets,recovery_budgets):
    assert member is selected and installed=="original-installed-declaration"
    assert budget==entry and job_budgets==job and recovery_budgets==recovery
    calls.append("supply")
    yield SimpleNamespace(facts={},runtime="original-runtime")
def execute(member,runtime):
    assert member is selected and runtime=="original-runtime"
    calls.append("execute")
    return {"configuration_forwarded":True}
inputs.load_admin_navigation_group=group
deployment.load_admin_deployment=load
supplier.supply_admin_runtime=supply
entry_module.execute_admin_navigation=execute
os.environ["LAB_JOB_OUTPUT_DIRECTORY"]="/unused-no-effects"
"""
    edits = {
        "complete": "",
        "implicit_defaults": "entry=AdminProductionBudgets()\n",
        "root_mismatch": "job=job.model_copy(update={'execution_seconds':21599})\n",
        "bad_recovery": "recovery=recovery.model_copy(update={'restore_seconds':True})\n",
        "insufficient_recovery_reserve": "job=job.model_copy(update={'cleanup_seconds':1000})\n",
    }
    program += edits[variant]
    program += """
try:
    result=entry_module.run_admin_navigation("original",Path("/unused-deployment"),budgets=entry,job_budgets=job,recovery_budgets=recovery,origin=None,allowed_actions=("noop",))
except ValueError:
    assert EXPECT_FAILURE and calls==[],calls
else:
    assert not EXPECT_FAILURE and result=={"configuration_forwarded":True}
    assert calls==["group","deployment","supply","execute"],calls
""".replace("EXPECT_FAILURE", str(variant != "complete"))
    result = run_child(program)
    assert result.returncode == 0, result.stdout + result.stderr


def test_map_budget_validation_precedes_input_selection_or_original_allocation() -> (
    None
):
    result = run_child(PRELUDE + """
import production_entry as module
assert "runtime-candidate" in module.__file__
called=[]
module.selected_navigation=lambda source: called.append(source)
for key,bad in (("execution_seconds",True),("cleanup_seconds",0)):
    try:
        module.run("original",Path("/unused"),job_budgets=job.model_copy(update={key:bad}),recovery_budgets=recovery)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid job budget accepted")
assert called==[]
""")
    assert result.returncode == 0, result.stdout + result.stderr


def test_same_installation_job_keeps_each_role_profile_identity_distinct_and_stable() -> (
    None
):
    result = run_child("""
import os
import deployment_preflight as map_install
import admin_production_installation as admin_install
os.environ["SLURM_JOB_ID"]="123456"
values=[]
for producer in (map_install,admin_install):
    for profile in ("a40","a100_40gb"):
        value=producer._installation_release_id(profile)
        assert value==producer._installation_release_id(profile)
        values.append(value)
assert len(set(values))==4,values
""")
    assert result.returncode == 0, result.stdout + result.stderr


def test_exact_outer_candidates_typecheck_with_original_dependencies(
    tmp_path: Path,
) -> None:
    # Full project static gate is shared by check_framework. This check covers
    # the seven actual outer consumers and software-evidence composer, consumers and their actual import order.
    paths = [
        MP / "runtime-candidate/production_entry.py",
        MP / "runtime-candidate/deployment_preflight.py",
        W
        / "experiments/framework-combined-release-20261030-v1/prepare_runtime_software.py",
        *(
            AP / "runtime-candidate" / name
            for name in (
                "admin_production_entry.py",
                "admin_production_supply.py",
                "admin_production_deployment.py",
                "admin_production_installation.py",
                "admin_production_member.py",
            )
        ),
    ]
    program = (
        "import subprocess,sys; result=subprocess.run([sys.executable,'-B','-m','mypy','--config-file',"
        + repr(str(I / "pyproject.toml"))
        + ",'--cache-dir',"
        + repr(str(tmp_path / "mypy"))
        + ",'--follow-imports=silent','--ignore-missing-imports',"
        + ",".join(repr(str(path)) for path in paths)
        + "]);sys.exit(result.returncode)"
    )
    result = run_child(program, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("is_map", [True, False])
def test_actual_candidate_group_recipe_types_remaining_boundary_and_actor_profile(
    is_map: bool,
) -> None:
    root = (MP if is_map else AP) / "runtime-candidate"
    model = MapProductionBudgets if is_map else AdminProductionBudgets
    entry = model.model_validate_json((root / "entry-budgets.json").read_bytes())
    job = OperationWindowBudgets.model_validate_json(
        (root / "job-budgets.json").read_bytes()
    )
    recovery = SourceRecoveryBudgets.model_validate_json(
        (root / "source-recovery-budgets.json").read_bytes()
    )
    assert entry.root_seconds == job.execution_seconds
    assert entry.site_seconds + entry.task_seconds <= entry.root_seconds
    assert (
        recovery.complete_recovery_path_seconds
        + 2 * entry.metadata_cleanup_seconds
        + entry.storage_cleanup_seconds
        <= job.cleanup_seconds
    )
    assert entry.generation_seconds == 600 and entry.interaction_seconds == 180
    assert entry.actor_rpc_cleanup_seconds == 60
    # This only verifies the selected provisional composition. The original
    # plan keeps actual timing/native closure/deployment unapproved.
    planned_wall = 18000 if is_map else 14400
    now = ManualClock().utcnow()
    owner = ResourceOwner(
        run_id="recipe-test", owner_id="reader", job_id="123", worker_id="reader"
    )
    end = now + timedelta(seconds=planned_wall - 600)
    assert job.minimum_remaining_seconds == planned_wall - 600
    window = job.window(owner, now=now, hard_end=end)
    assert (
        window.hard_end - window.cleanup_deadline
    ).total_seconds() == job.final_margin_seconds
    with pytest.raises(ValueError, match="Insufficient"):
        job.window(owner, now=now + timedelta(seconds=0.001), hard_end=end)


def test_closed_original_trace_read_uses_remaining_cleanup_after_execution_expiry(
    tmp_path: Path,
) -> None:
    data = trace_fixture(tmp_path)
    journal = data.journal()
    clock, cancellation = ManualClock(), CancelSwitch()
    clock.wall = datetime.now(timezone.utc)
    owner = data.plan.scope.owner
    window = OperationTimeWindow(
        owner=owner,
        execution_deadline=clock.utcnow() + timedelta(seconds=10),
        cleanup_deadline=clock.utcnow() + timedelta(seconds=20),
        hard_end=clock.utcnow() + timedelta(seconds=21),
    )
    journal.controls = BoundedOperationControls(
        OperationGuards(clock, cancellation), clock, window
    )
    snapshot = journal.create(data.plan, command("create", attempt="attempt"))
    for event in data.events():
        snapshot = journal.append(event, snapshot.revision, event.operation)
    assert snapshot.project().sealed is not None
    original = command("original-run-read").model_copy(
        update={"deadline": window.execution_deadline}
    )
    before = (tmp_path / "journal" / journal.file.name).read_bytes()
    clock.sleep(10)
    cancellation.cancelled = True
    with pytest.raises(OperationStopped):
        journal.read(original)
    read = original.cleanup("closed-trace-review-read", now=clock.utcnow(), seconds=10)
    assert read.parent_operation_id == original.operation_id
    assert read.cancellation_ref is None and read.mode == "cleanup"
    assert journal.read(read) == snapshot
    assert (tmp_path / "journal" / journal.file.name).read_bytes() == before
    clock.sleep(10)
    with pytest.raises(OperationStopped):
        journal.read(read)
