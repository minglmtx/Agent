"""Final data factory on original unit source/claim, never a live permission.

Reuse the qualified source/claim fixture with explicit native/kernel/model
premises. Normal binding must remain unacquired; original runtime cancel/partial
and cleanup evidence is reused, not inferred from these configuration tests.
"""

from datetime import timedelta
from pathlib import Path
from typing import Any
import pytest
from admin_production_execution import (
    site_acquisition_context,
    bind_admin_production_execution,
)
from admin_navigation_owned_fixtures import owned_navigation_case
from test_admin_production_task_plan import frozen_case
from test_admin_navigation_input import contracts as contracts
from site_instance_fixtures import node_path as node_path
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from lab_generate_skill.domain.task_initialization import TaskActorInitialization
from lab_generate_skill.domain.trace_plan import TraceCapacity


@pytest.fixture
def bound_case(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, contracts: Any
) -> Any:
    # owned_navigation_case needs this already existing root.
    return owned_navigation_case(tmp_path, node_path, monkeypatch, contracts)


def arguments(c: Any, root: Path) -> dict[str, Any]:
    resources = c.owned.resources
    base = c.source.site
    frozen = frozen_case(c)
    actor = TaskActorInitialization(
        candidate_id=frozen.policy.candidate_id,
        revision_round=0,
        context_configuration_ref=frozen.context_ref,
        memory=frozen.policy.memory,
        model_allocation=resources.model.binding.resource,
        parameters_refs=(frozen.parameters_ref,),
        generation_seconds=60,
        interaction_seconds=60,
        cleanup_seconds=60,
    )
    return dict(
        declarations=c.declarations,
        owner=resources.owner,
        source=c.admitted.reader,
        model=resources.model,
        site=resources.site.spec,
        acquisition=site_acquisition_context(
            resources.site.spec,
            c.declarations.plan.read_operation,
            c.declarations.plan,
            base.clock,
            seconds=120,
        ),
        template=c.source.qualified.material.browser.configuration,
        actor=actor,
        journal=base.journal,
        bindings=c.admitted.bindings,
        controls=base.controls,
        clock=base.clock,
        trace_root=root / "new-trace",
        calls_root=root / "new-calls",
        trace_capacity=TraceCapacity(
            max_events=128,
            max_bytes=4194304,
            max_event_bytes=65536,
            max_trace_bytes=4194304,
        ),
    )


def snapshot(c: Any) -> dict[str, bytes]:
    return {
        f.name: f.read_bytes()
        for f in c.source.site.journal._root.glob("*.resource.json")
    }


def test_original_claim_browser_codec_and_owned_factory_no_acquisition(
    bound_case: Any, tmp_path: Path
) -> None:
    c = bound_case
    inputs = arguments(c, tmp_path)
    before = snapshot(c)
    original = bind_admin_production_execution(**inputs)
    assert original.resources.owner is c.owned.resources.owner
    assert original.resources.model is c.owned.resources.model
    assert original.resources.site.spec == c.owned.resources.site.spec
    assert original.resources.site.phase == "new"
    assert original.resources.browser() is None
    assert original.bundle.task.plan == c.declarations.plan
    assert snapshot(c) == before


@pytest.mark.parametrize("fault", ["expired", "owner", "installation", "task"])
def test_final_mismatch_or_expiration_before_any_resource(
    bound_case: Any, tmp_path: Path, fault: str
) -> None:
    c = bound_case
    inputs = arguments(c, tmp_path)
    before = snapshot(c)
    if fault == "expired":
        inputs["acquisition"] = inputs["acquisition"].model_copy(
            update={"deadline": c.source.site.clock.utcnow() - timedelta(seconds=1)}
        )
    elif fault == "owner":
        s = inputs["site"]
        token = s.token.model_copy(
            update={"owner": s.token.owner.model_copy(update={"owner_id": "other"})}
        )
        inputs["site"] = s.model_copy(
            update={
                "configuration": s.configuration.model_copy(update={"token": token})
            }
        )
    elif fault == "installation":
        template = inputs["template"]
        i = template.installation
        inputs["template"] = template.model_copy(
            update={
                "installation": i.model_copy(
                    update={"python_executable": i.python_executable + "-foreign"}
                )
            }
        )
    else:
        d = inputs["declarations"]
        from dataclasses import replace

        inputs["declarations"] = replace(
            d,
            plan=d.plan.model_copy(
                update={
                    "operation": d.plan.operation.model_copy(
                        update={"operation_id": "foreign-task"}
                    )
                }
            ),
        )
    with pytest.raises((OwnershipConflict, OperationStopped, ValueError)):
        bind_admin_production_execution(**inputs)
    assert snapshot(c) == before


def test_site_budget_starts_at_first_handoff_and_clamps_existing_deadlines(
    bound_case: Any,
) -> None:
    c = bound_case
    original_clock = c.source.site.clock
    now = original_clock.utcnow()

    class HandoffClock:
        def __init__(self, offset: int) -> None:
            self.offset = offset

        def utcnow(self) -> Any:
            return now + timedelta(seconds=self.offset)

        def monotonic(self) -> float:
            return 50.0

        def sleep(self, seconds: float) -> None:
            raise AssertionError("Pure declaration must not sleep")

    parent = c.declarations.plan.read_operation
    site = c.owned.resources.site.spec
    first = site_acquisition_context(
        site, parent, c.declarations.plan, HandoffClock(0), seconds=60
    )
    later = site_acquisition_context(
        site, parent, c.declarations.plan, HandoffClock(50), seconds=60
    )
    assert first.deadline == min(
        parent.deadline,
        c.declarations.plan.operation.deadline,
        now + timedelta(seconds=60),
    )
    assert later.deadline == min(
        parent.deadline,
        c.declarations.plan.operation.deadline,
        now + timedelta(seconds=110),
    )
    assert later.deadline > first.deadline
    invalid: tuple[Any, ...] = (True, 0, 7201, "60")
    for bad in invalid:
        with pytest.raises(ValueError, match="bounded"):
            site_acquisition_context(
                site, parent, c.declarations.plan, original_clock, seconds=bad
            )
