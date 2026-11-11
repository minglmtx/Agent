"""Canonical Admin supplier/entry join and current-node origin probe.

Join tests explicitly replace effects and never grant a source/model/site.
The one kernel probe runs only inside the actual Slurm software allocation.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
import admin_production_entry as entry
import admin_production_inputs as inputs
import admin_production_supply as supply
import admin_production_deployment as deployment
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.network.loopback_ports import LoopbackPorts
from lab_generate_skill.domain.lifecycle import OperationContext, CancellationRef
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_slurm_commands import Cancel, guard
from test_linux_cgroups import actual_slurm_execution
from admin_production_task_plan import AdminProductionBudgets
from lab_generate_skill.domain.operation_window import OperationWindowBudgets
from lab_generate_skill.domain.source_recovery_budget import SourceRecoveryBudgets

# Exact candidate configuration is a fixture for the intercepted entry only, not a
# runtime approval for the repaired candidate or this short software allocation.
RUNTIME = inputs.PACKAGE / "runtime-repair-candidate"
ENTRY_BUDGETS = AdminProductionBudgets.model_validate_json(
    (RUNTIME / "entry-budgets.json").read_bytes()
)
JOB_BUDGETS = OperationWindowBudgets.model_validate_json(
    (RUNTIME / "job-budgets.json").read_bytes()
)
RECOVERY_BUDGETS = SourceRecoveryBudgets.model_validate_json(
    (RUNTIME / "source-recovery-budgets.json").read_bytes()
)


@pytest.fixture(scope="module")
def original_group() -> tuple[inputs.SelectedAdminNavigation, ...]:
    return inputs.load_admin_navigation_group(guard(60))


def join_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    group: tuple[inputs.SelectedAdminNavigation, ...],
    fault: str = "none",
) -> tuple[list[str], dict[str, Any]]:
    events: list[str] = []
    facts: dict[str, Any] = {"engineering_only": True}
    runtime = object()
    accepted = object()
    monkeypatch.setenv("LAB_JOB_OUTPUT_DIRECTORY", str(tmp_path))

    def selected(control: Any) -> tuple[inputs.SelectedAdminNavigation, ...]:
        events.append("group")
        return group

    def load(*args: Any) -> object:
        events.append("deployment")
        return accepted

    @contextmanager
    def supplied(*args: Any, **kwargs: Any) -> Iterator[SimpleNamespace]:
        assert args[0] is group[0] and args[1] is accepted
        assert args[3] is None and args[4] == ("send_msg_to_user",)
        assert args[5] == tmp_path
        assert args[2] == ENTRY_BUDGETS
        assert kwargs == dict(
            job_budgets=JOB_BUDGETS, recovery_budgets=RECOVERY_BUDGETS
        )
        events.append("supply")
        try:
            yield SimpleNamespace(runtime=runtime, facts=facts)
        finally:
            events.append("cleanup")
            facts["metadata_admission_revoked"] = True
            if fault == "cleanup":
                raise OSError("unit cleanup error after known result")

    def execute(member: Any, actual: Any) -> dict[str, Any]:
        assert member is group[0] and actual is runtime
        events.append("execute")
        if fault == "business":
            raise OSError("unit business entry error")
        return {"business_result": "unit_only", "actual_actor_members_executed": []}

    monkeypatch.setattr(inputs, "load_admin_navigation_group", selected)
    monkeypatch.setattr(deployment, "load_admin_deployment", load)
    monkeypatch.setattr(supply, "supply_admin_runtime", supplied)
    monkeypatch.setattr(entry, "execute_admin_navigation", execute)
    return events, facts


@pytest.mark.parametrize("fault", ["none", "business", "cleanup"])
def test_canonical_join_keeps_one_group_supply_business_and_cleanup(
    original_group: tuple[inputs.SelectedAdminNavigation, ...],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fault: str,
) -> None:
    events, facts = join_fixture(monkeypatch, tmp_path, original_group, fault)
    source_id = original_group[0].private.task.source_task_id
    if fault == "none":
        result = entry.run_admin_navigation(
            source_id,
            tmp_path / "deployment.json",
            origin=None,
            allowed_actions=("send_msg_to_user",),
            budgets=ENTRY_BUDGETS,
            job_budgets=JOB_BUDGETS,
            recovery_budgets=RECOVERY_BUDGETS,
        )
        assert result is facts and result["metadata_admission_revoked"] is True
    else:
        with pytest.raises(OSError, match="unit"):
            entry.run_admin_navigation(
                source_id,
                tmp_path / "deployment.json",
                origin=None,
                allowed_actions=("send_msg_to_user",),
                budgets=ENTRY_BUDGETS,
                job_budgets=JOB_BUDGETS,
                recovery_budgets=RECOVERY_BUDGETS,
            )
    assert events == ["group", "deployment", "supply", "execute", "cleanup"]
    if fault != "business":
        assert facts["business_result"] == "unit_only"
        assert facts["actual_actor_members_executed"] == []


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "duplicate",
        "empty",
        "wrong_type",
        "actions_empty",
        "actions_repeat",
        "actions_unknown",
        "origin_bad",
    ],
)
def test_invalid_selector_or_configuration_cannot_reach_supplier(
    original_group: tuple[inputs.SelectedAdminNavigation, ...],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fault: str,
) -> None:
    group = (
        original_group
        if fault != "duplicate"
        else (original_group[0], original_group[0])
    )
    events, _ = join_fixture(monkeypatch, tmp_path, group)
    source: Any = original_group[0].private.task.source_task_id
    actions: tuple[str, ...] = ("send_msg_to_user",)
    origin: Any = None
    if fault == "missing":
        source = "not-a-selected-member"
    if fault == "empty":
        source = ""
    if fault == "wrong_type":
        source = True
    if fault == "actions_empty":
        actions = ()
    if fault == "actions_repeat":
        actions = ("send_msg_to_user", "send_msg_to_user")
    if fault == "actions_unknown":
        actions = ("unit_not_an_actor_action",)
    if fault == "origin_bad":
        origin = "http://example.invalid/admin"
    with pytest.raises((ValueError, TypeError)):
        entry.run_admin_navigation(
            source,
            tmp_path / "deployment.json",
            origin=origin,
            allowed_actions=actions,
            budgets=ENTRY_BUDGETS,
            job_budgets=JOB_BUDGETS,
            recovery_budgets=RECOVERY_BUDGETS,
        )
    assert events == (["group"] if fault in ("missing", "duplicate") else [])


def probe_context() -> tuple[OperationContext, OperationGuards, SystemClock, Cancel]:
    execution, _ = actual_slurm_execution()
    clock = SystemClock()
    cancel = Cancel()
    op = OperationContext(
        operation_id="admin-probe-test",
        run_id="admin-probe-" + execution.job_id,
        owner_id="admin-probe-owner",
        deadline=clock.utcnow() + timedelta(seconds=30),
    )
    return op, OperationGuards(clock, cancel), clock, cancel


def test_actual_node_probe_releases_before_original_exact_reservation() -> None:
    op, controls, clock, _ = probe_context()
    origin = supply.measure_admin_origin(
        op, controls, clock, probe_seconds=10, cleanup_seconds=10
    )
    # A released probe is no authority: the original adapter must reserve again.
    lease = LoopbackPorts(required_prefix=(origin.web_port,)).reserve(1, guard(10))
    try:
        assert lease.ports == (origin.web_port,)
    finally:
        lease.release(guard(10))


@pytest.mark.parametrize("fault", ["cancel", "invalid_and_close", "reserve_error"])
def test_origin_probe_cancel_and_failure_keep_cleanup(
    monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    op, controls, clock, cancel = probe_context()
    op = op.model_copy(
        update={
            "cancellation_ref": CancellationRef(
                run_id=op.run_id, owner_id=op.owner_id, channel_id="probe-cancel"
            )
        }
    )
    events: list[str] = []
    cleanup_error = OSError("unit original port close failed")

    class Lease:
        @property
        def ports(self) -> tuple[int, ...]:
            cancel.cancelled = True
            return (0 if fault == "invalid_and_close" else 19001,)

        def release(self, control: Any) -> None:
            control.checkpoint()  # must be independent of execute cancellation
            events.append("release")
            if fault == "invalid_and_close":
                raise cleanup_error

    class Ports:
        def reserve(self, count: int, control: Any) -> Lease:
            assert count == 1
            control.checkpoint()
            events.append("reserve")
            if fault == "reserve_error":
                raise OSError("unit reserve failed before lease returned")
            return Lease()

    monkeypatch.setattr(supply, "LoopbackPorts", Ports)
    if fault == "cancel":
        with pytest.raises(OperationStopped) as stopped:
            supply.measure_admin_origin(
                op, controls, clock, probe_seconds=10, cleanup_seconds=10
            )
        assert stopped.value.reason_code == "CANCELLED"
        assert events == ["reserve", "release"]
    elif fault == "invalid_and_close":
        with pytest.raises(BaseExceptionGroup) as grouped:
            supply.measure_admin_origin(
                op, controls, clock, probe_seconds=10, cleanup_seconds=10
            )
        assert isinstance(grouped.value.exceptions[0], ValueError)
        assert grouped.value.exceptions[1] is cleanup_error
        assert events == ["reserve", "release"]
    else:
        with pytest.raises(OSError, match="unit reserve failed"):
            supply.measure_admin_origin(
                op, controls, clock, probe_seconds=10, cleanup_seconds=10
            )
        assert events == ["reserve"]


@pytest.mark.parametrize(
    "probe,close", [(0, 10), (31, 10), (True, 10), (10, 0), (10, 61), (10, False)]
)
def test_probe_limits_reject_before_any_effect(probe: Any, close: Any) -> None:
    unused: Any = None
    with pytest.raises(ValueError, match="bounded"):
        supply.measure_admin_origin(
            unused, unused, unused, probe_seconds=probe, cleanup_seconds=close
        )
