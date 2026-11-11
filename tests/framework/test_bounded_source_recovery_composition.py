"""Original source ports with one shared time window under unit native premises.

SQL/services/page/kernel/rights are the existing explicit doubles. Actual Slurm
caller reads remain original. No real source/Actor/claim or training grant.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import os
from typing import Any

import pytest

from lab_generate_skill.domain.lifecycle import OperationContext, ResourceOwner
from lab_generate_skill.domain.operation_window import OperationTimeWindow
from lab_generate_skill.domain.source_recovery_budget import SourceRecoveryBudgets
from lab_generate_skill.ports.lifecycle import (
    Clock,
    CancellationReader,
    OperationControl,
)
from lab_generate_skill.runtime.bounded_lifecycle import BoundedOperationControls
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.bootstrap.source_browser_assets import SourceBrowserAssets
from lab_generate_skill.domain.errors import OperationStopped
from map_registered_worker_fixtures import RegisteredMapCase
from test_source_recovery_budget_consumers import source_case as source_case
from test_source_recovery_budget_consumers import contracts as contracts
from test_source_recovery_budget_consumers import node_path as node_path
from test_map_source_qualification import (
    test_source_initializer_unique_initial_observation_restore_reset_and_close_before_publication as map_case,
)
from test_admin_navigation_source_composition import original_source_unit_case
from gitlab_group_source_fixtures import group_source_unit_case
from test_gitlab_group_source_composition import contracts_for
import site_resource_fixtures
import lab_generate_skill.bootstrap.admin_navigation_source_qualification as admin_source
import lab_generate_skill.bootstrap.gitlab_group_source_qualification as group_source

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")


@dataclass
class WindowFixture:
    offset: float = 0
    created: list[BoundedOperationControls] = field(default_factory=list)


class OffsetClock:
    def __init__(self, original: Clock, state: WindowFixture) -> None:
        self.original, self.state = original, state

    def utcnow(self) -> datetime:
        return self.original.utcnow() + timedelta(seconds=self.state.offset)

    def monotonic(self) -> float:
        return self.original.monotonic() + self.state.offset

    def sleep(self, seconds: float) -> None:
        self.original.sleep(seconds)


class OriginalFixtureControls:
    def __init__(
        self, clock: Clock, cancellation: CancellationReader, state: WindowFixture
    ) -> None:
        self.clock, self.cancellation, self.state = clock, cancellation, state
        self.current: BoundedOperationControls | None = None

    def bind(self, operation: OperationContext) -> OperationControl:
        if self.current is None:
            now = self.clock.utcnow()
            owner = ResourceOwner(
                run_id=operation.run_id,
                owner_id=operation.owner_id,
                job_id=os.environ["SLURM_JOB_ID"],
                worker_id="explicit-unit-window",
            )
            window = OperationTimeWindow(
                owner=owner,
                execution_deadline=now + timedelta(seconds=60),
                cleanup_deadline=now + timedelta(seconds=660),
                hard_end=now + timedelta(seconds=720),
            )
            self.current = BoundedOperationControls(
                OperationGuards(self.clock, self.cancellation),
                OffsetClock(self.clock, self.state),
                window,
            )
            self.state.created.append(self.current)
        return self.current.bind(operation)


@pytest.fixture(autouse=True)
def window_controls(monkeypatch: pytest.MonkeyPatch) -> WindowFixture:
    state = WindowFixture()

    def factory(
        clock: Clock, cancellation: CancellationReader
    ) -> OriginalFixtureControls:
        return OriginalFixtureControls(clock, cancellation, state)

    monkeypatch.setattr(site_resource_fixtures, "OperationGuards", factory)
    return state


def recovery(site: str) -> SourceRecoveryBudgets:
    package = (
        "framework-map-navigation42-production-20261102-v1"
        if site == "map"
        else "framework-admin-navigation-production-20261102-v1"
    )
    return SourceRecoveryBudgets.model_validate_json(
        (
            W
            / "experiments"
            / package
            / "runtime-candidate/source-recovery-budgets.json"
        ).read_bytes()
    )


@pytest.mark.parametrize("cancel,lost", [(False, False), (True, False), (False, True)])
def test_original_map_source_with_window_and_selected_recovery_profile(
    source_case: tuple[
        RegisteredMapCase, OriginalSourceQualificationOwner, SourceBrowserAssets
    ],
    monkeypatch: pytest.MonkeyPatch,
    window_controls: WindowFixture,
    cancel: bool,
    lost: bool,
) -> None:
    map_case(source_case, monkeypatch, cancel, lost, recovery_budgets=recovery("map"))
    assert window_controls.created


@pytest.mark.parametrize(
    "fault",
    ["none", "cancel_after_reset", "restore_return_lost", "deadline_after_reset"],
)
@pytest.mark.parametrize("site", ["admin", "group"])
def test_original_source_window_normal_cancel_partial_commit_and_expiry_after_reset(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    window_controls: WindowFixture,
    site: str,
    fault: str,
) -> None:
    module = admin_source if site == "admin" else group_source
    if fault == "deadline_after_reset":
        original = getattr(module, "restore_source")

        def expire_after_actual_reset(*args: Any, **kwargs: Any) -> None:
            original(*args, **kwargs)
            assert args[0].progress.reset.status == "safe"
            window_controls.offset = 61

        monkeypatch.setattr(module, "restore_source", expire_after_actual_reset)
    if site == "admin":
        result = original_source_unit_case(
            tmp_path,
            node_path,
            monkeypatch,
            contracts,
            fault,
            recovery_budgets=recovery("admin"),
        )
    else:
        import gitlab_group_fixtures as inputs

        source = "286d4ac488bdcd446ffc"
        monkeypatch.setattr(
            inputs,
            "FIXTURE",
            W
            / "experiments/sft-ordinary-source-bindings-v1/prepared/contracts"
            / (source + ".json"),
        )
        selected = contracts_for(source)
        result = group_source_unit_case(
            tmp_path,
            node_path,
            monkeypatch,
            selected,
            fault,
            recovery_budgets=recovery("admin"),
        )
    assert window_controls.created
    if fault == "none":
        assert result.qualified is not None and result.facts.reset.status == "safe"
    else:
        assert result.qualified is None and result.facts is None
    if fault == "deadline_after_reset":
        assert isinstance(result.failure.primary, OperationStopped)
        assert result.failure.primary.reason_code == "DEADLINE_EXCEEDED"
        assert result.failure.progress.reset.status == "safe"
        assert result.failure.cleanup_errors == ()
        assert result.failure.actual_actor_dispatched is False
