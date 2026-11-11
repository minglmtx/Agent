"""Pure real-owner composition over explicit synthetic claim/source premises."""

from dataclasses import replace
from pathlib import Path
from typing import Any, cast
import pytest
from lab_generate_skill.bootstrap.map_owned_execution import (
    map_navigation_owned_execution,
)
from lab_generate_skill.bootstrap.map_task_execution_bindings import (
    MapTaskExecutionDeclarations,
)
from lab_generate_skill.adapters.sites.claimed_authority import (
    ClaimedSiteResourceAuthority,
)
from lab_generate_skill.adapters.sites.task_site_authority import TaskSiteAuthority
from lab_generate_skill.domain.trace_plan import TraceCapacity
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.ports.task_bindings import TaskBindings
from task_resource_owner_fixtures import owned_task
from site_instance_fixtures import node_path as node_path


def test_default_factory_uses_original_owners_and_rejects_dynamic_origin_before_effects(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with owned_task(node_path, monkeypatch) as (c, r):
        from contextlib import contextmanager
        from collections.abc import Iterator
        from lab_generate_skill.adapters.plans.closed_actor_inputs import (
            SupervisedActorAcquisitionReads,
        )
        from lab_generate_skill.domain.lifecycle import OperationContext

        lifecycle: list[str] = []

        class UnitActorInputs(SupervisedActorAcquisitionReads):
            """Only the scope seam; original dynamic origin must still refuse."""

            def __init__(self) -> None:
                pass

            @contextmanager
            def task_scope(self, operation: OperationContext) -> Iterator[None]:
                assert operation == c.p.plan.operation
                lifecycle.append("enter")
                try:
                    yield
                finally:
                    lifecycle.append("exit")

        r.model.acquisition_reads = UnitActorInputs()
        old, p = c.bundle, c.p
        d = MapTaskExecutionDeclarations(
            p.plan,
            p.declaration,
            p.reset,
            old.capture.declaration,
            old.capture.declaration_ref,
            old.finalization.declaration,
            old.finalization.declaration_ref,
        )

        def declarations(*args: object, **kwargs: object) -> Any:
            pytest.fail("Unqualified dynamic origin may not reach browser factory")

        owned = map_navigation_owned_execution(
            d,
            r.owner,
            c.journals.source_reader,
            r.model,
            r.site.spec,
            r.site.operation,
            declarations,
            journal=p.original.resource.journal,
            bindings=p.source.native.bindings,
            controls=p.original.resource.controls,
            clock=p.original.resource.clock,
            trace_root=p.original.workspace / "owned-trace",
            calls_root=p.original.workspace / "owned-calls",
            trace_capacity=TraceCapacity(
                max_events=128,
                max_bytes=4 * 1024**2,
                max_event_bytes=65536,
                max_trace_bytes=4 * 1024**2,
            ),
        )
        assert owned.resources.site.phase == "new" and owned.resources.browser() is None
        assert owned.resources.inputs is not None
        assert owned.bundle.preparation.declared_inputs is (
            owned.resources.inputs.preparation_declarations
        )
        source = owned.resources.site.authority
        assert isinstance(source, TaskSiteAuthority)
        assert source.source is owned.physical_site and isinstance(
            owned.physical_site.source, ClaimedSiteResourceAuthority
        )
        assert c.native.loader.session.calls == 0 and p.requests == []
        # Existing fixture deliberately has dynamic origin; production suppliers
        # require its qualified frozen source, and must stop before worker/RPC.
        with pytest.raises((TaskExecutionUnconfirmed, BaseExceptionGroup)):
            owned.bundle.task.execute(p.plan.intent, p.plan.operation)
        assert c.native.loader.session.calls == 0 and p.requests == []
        assert not p.original.resource.channels
        assert owned.resources.site.phase != "open"
        assert lifecycle == ["enter", "exit"]


@pytest.mark.parametrize("value", [None, "owner", 0, {}, []])
def test_default_factory_invalid_inputs_have_no_effect(value: Any) -> None:
    with pytest.raises(TypeError):
        map_navigation_owned_execution(
            value,
            value,
            value,
            value,
            value,
            value,
            value,
            journal=value,
            bindings=value,
            controls=value,
            clock=value,
            trace_root=value,
            calls_root=value,
            trace_capacity=value,
        )
