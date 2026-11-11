"""Original controller bounds: strict bytes/identity, finite end and live read."""

from datetime import datetime, timedelta, timezone
import json
from typing import Any

import pytest

from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.slurm.commands import SlurmCommandRunner
from lab_generate_skill.adapters.slurm.job_time import (
    parse_job_time_limit,
    observe_job_time_limit,
)
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_current_cgroup
from lab_generate_skill.domain.lifecycle import ResourceOwner
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.operation_window import OperationWindowBudgets
from lab_generate_skill.domain.slurm_job_time import SlurmJobTimeLimit
from lab_generate_skill.bootstrap.original_job_time import original_job_controls
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_slurm_allocation_codecs import controller, original_identity
from test_linux_cgroups import actual_slurm_execution
from test_slurm_probe import NoCancel
from allocation_fixtures import QueryRunner


def data() -> tuple[dict[str, Any], datetime]:
    value = controller()
    start = original_identity().started_at_epoch
    value["jobs"][0]["time_limit"] = {"set": True, "infinite": False, "number": 60}
    value["jobs"][0]["end_time"] = {
        "set": True,
        "infinite": False,
        "number": start + 3600,
    }
    return value, datetime.fromtimestamp(start + 1, timezone.utc)


def test_scalar_time_roundtrip_and_repeat_do_not_grant_authority() -> None:
    value, observed = data()
    for _ in range(2):
        limit = parse_job_time_limit(
            json.dumps(value).encode(), original_identity(), "a0125", observed
        )
        assert limit.time_limit_minutes == 60
        assert limit.hard_end.timestamp() == original_identity().started_at_epoch + 3600
        assert SlurmJobTimeLimit.model_validate_json(limit.model_dump_json()) == limit
        assert not hasattr(limit, "permission")


@pytest.mark.parametrize("field", ["end_time", "time_limit"])
@pytest.mark.parametrize(
    "bad",
    [
        None,
        1,
        {},
        {"set": False, "infinite": False, "number": 1},
        {"set": True, "infinite": True, "number": 1},
        {"set": True, "infinite": False, "number": True},
        {"set": True, "infinite": False, "number": 0},
        {"set": True, "infinite": False, "number": -1},
    ],
)
def test_unknown_infinite_wrong_and_zero_time_refused(field: str, bad: object) -> None:
    value, observed = data()
    value["jobs"][0][field] = bad
    with pytest.raises(ValueError):
        parse_job_time_limit(
            json.dumps(value).encode(), original_identity(), "a0125", observed
        )


@pytest.mark.parametrize(
    "field,bad",
    [
        ("job_state", ["PENDING"]),
        ("restart_cnt", 1),
        ("user_id", 1),
        ("cluster", "foreign"),
    ],
)
def test_wrong_original_identity_refused(field: str, bad: object) -> None:
    value, observed = data()
    value["jobs"][0][field] = bad
    with pytest.raises(ValueError):
        parse_job_time_limit(
            json.dumps(value).encode(), original_identity(), "a0125", observed
        )


def test_end_limit_and_observation_edges() -> None:
    value, observed = data()
    start = original_identity().started_at_epoch
    for end in (start, 10**100):
        value["jobs"][0]["end_time"]["number"] = end
        with pytest.raises(ValueError):
            parse_job_time_limit(
                json.dumps(value).encode(), original_identity(), "a0125", observed
            )
    value, observed = data()
    for delta in (-1, 2):
        value["jobs"][0]["end_time"]["number"] = start + 3600 + delta
        limit = parse_job_time_limit(
            json.dumps(value).encode(), original_identity(), "a0125", observed
        )
        assert limit.controller_end.timestamp() == start + 3600 + delta
        assert limit.hard_end.timestamp() == start + 3600 + min(delta, 0)
    value, observed = data()
    for moment in (
        datetime.fromtimestamp(start - 1, timezone.utc),
        observed + timedelta(seconds=3599),
    ):
        with pytest.raises(ValueError):
            parse_job_time_limit(
                json.dumps(value).encode(), original_identity(), "a0125", moment
            )


def test_observer_single_attempt_preserves_original_query_and_rejects_cancel() -> None:
    value, observed = data()
    runner = QueryRunner()
    runner.controller = json.dumps(value).encode()

    class FixedClock(SystemClock):
        def utcnow(self) -> datetime:
            return observed

    read = observe_job_time_limit(
        original_identity(),
        "a0125",
        DeadlineControl(5, "unit-query"),
        FixedClock(),
        runner=runner,
    )
    assert len(runner.calls) == 1 and read.capture.stdout == runner.controller
    assert read.limit.execution == original_identity()
    runner.fail = RuntimeError("query cancelled with unknown return")
    with pytest.raises(RuntimeError) as caught:
        observe_job_time_limit(
            original_identity(),
            "a0125",
            DeadlineControl(5, "unit-query-2"),
            FixedClock(),
            runner=runner,
        )
    assert caught.value is runner.fail and len(runner.calls) == 2


def test_actual_original_allocation_end_caps_controls_without_resources() -> None:
    execution, _ = actual_slurm_execution()
    writer = current_process_identity()
    before = observe_current_cgroup(
        execution, writer, DeadlineControl(15, "actual-time-kernel")
    )
    clock = SystemClock()
    owner = ResourceOwner(
        run_id="live-time-read",
        owner_id="reader",
        job_id=execution.job_id,
        worker_id="reader",
    )
    budget = OperationWindowBudgets(
        execution_seconds=1,
        cleanup_seconds=2,
        final_margin_seconds=1,
        stop_signal_lead_seconds=3,
    )
    controls, observation = original_job_controls(
        execution,
        owner,
        writer.node_id,
        budget,
        OperationGuards(clock, NoCancel()),
        clock,
        DeadlineControl(15, "actual-time-controller"),
    )
    after = observe_current_cgroup(
        execution, writer, DeadlineControl(15, "actual-time-kernel-after")
    )
    assert before.membership == after.membership
    assert controls.window.hard_end == observation.limit.hard_end
    # No website/model/claim/acquisition or retained instance is created.


@pytest.mark.parametrize("fault", ["owner", "copied_bad_budget"])
def test_original_time_assembly_rejects_before_controller_query(
    monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    import lab_generate_skill.bootstrap.original_job_time as assembly

    def query(*args: object, **kwargs: object) -> None:
        raise AssertionError("Invalid budget/owner reached actual controller")

    monkeypatch.setattr(assembly, "observe_job_time_limit", query)
    execution = original_identity()
    owner = ResourceOwner(
        run_id="read", owner_id="owner", job_id=execution.job_id, worker_id="reader"
    )
    budget = OperationWindowBudgets(
        execution_seconds=1,
        cleanup_seconds=2,
        final_margin_seconds=1,
        stop_signal_lead_seconds=3,
    )
    if fault == "owner":
        owner = owner.model_copy(update={"job_id": "999"})
    else:
        budget = budget.model_copy(update={"execution_seconds": True})
    clock = SystemClock()
    with pytest.raises(OwnershipConflict if fault == "owner" else ValueError):
        original_job_controls(
            execution,
            owner,
            "a0125",
            budget,
            OperationGuards(clock, NoCancel()),
            clock,
            DeadlineControl(5, "unit-no-query"),
        )
