"""Actual suppliers, synthetic service/kernel premises; no real task permission."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.browsergym.task_owner import OriginalTaskBrowserOwner
from lab_generate_skill.adapters.sites.task_nonstart_authority import (
    OriginalTaskNonstartAuthority,
)
from lab_generate_skill.domain.errors import OwnershipConflict, DispatchAlreadyCommitted
from lab_generate_skill.domain.task_finalization import UnstartedTaskBrowser
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from task_resource_owner_fixtures import owned_task
from preparation_record_fixtures import put
from site_instance_fixtures import node_path as node_path
import traceback


def test_original_owner_default_initial_actor_capture_reset_close(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with owned_task(node_path, monkeypatch) as (c, r):
        try:
            result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
        except TaskExecutionUnconfirmed as error:
            if error.primary is not None:
                traceback.print_exception(error.primary)
            for failure in error.cleanup_errors:
                traceback.print_exception(failure)
            raise
        assert result.evaluation.status == "success"
        assert c.native.loader.session.calls == 1
        assert c.bundle.finalization.state.reset is not None
        assert c.bundle.finalization.state.reset.status == "safe"
        browser = r.browser()
        assert browser is not None and browser.phase == "closed"
        assert c.bundle.preparation.state.result is not None
        assert c.bundle.initialization.original().state.baseline is not None
        equivalence = c.bundle.initialization.original().state.equivalence
        assert equivalence is not None and equivalence.status == "equivalent"
        with pytest.raises(DispatchAlreadyCommitted):
            c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)


@pytest.mark.parametrize("fault", ["source", "foreign", "factory", "registered"])
def test_original_nonstart_never_infers_from_unconfirmed_state(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with owned_task(node_path, monkeypatch) as (c, r):
        plan, d = c.p.plan, c.bundle.finalization.declaration
        holder = r.browser_owner
        op = plan.operation.cleanup(
            d.browser_close_operation_id,
            now=c.p.original.resource.clock.utcnow(),
            seconds=30,
        ).model_copy(
            update={
                "allocation_id": holder.token.allocation_id,
                "recovery_ref": holder.token.recovery_ref,
            }
        )
        observed = UnstartedTaskBrowser(
            scope=c.p.reset.scope,
            token=holder.token,
            operation=op,
            reset_plan_ref=plan.reset_plan_ref,
            preparation_declaration_ref=plan.declaration_ref,
            finalization_declaration_ref=c.bundle.finalization.declaration_ref,
            owner_phase="not_constructed",
        )
        ref = put(c.p.original.resource.evidence, observed)
        a = OriginalTaskNonstartAuthority(r)
        if fault == "source":
            c.journals.claim_authority.denied = True
        elif fault == "factory":
            holder.begin()
        elif fault == "registered":
            holder.journal.register(
                holder.token,
                op.model_copy(update={"mode": "execute", "parent_operation_id": None}),
            )
        if fault == "foreign":
            with ThreadPoolExecutor(max_workers=1) as pool:
                with pytest.raises(OwnershipConflict):
                    pool.submit(
                        a.close_unstarted,
                        plan,
                        d,
                        observed,
                        ref,
                        op,
                        c.p.original.resource.controls.bind(op),
                    ).result()
        else:
            with pytest.raises((OwnershipConflict, PermissionError)):
                a.close_unstarted(
                    plan, d, observed, ref, op, c.p.original.resource.controls.bind(op)
                )
        assert not holder.sealed and c.native.loader.session.calls == 0


def test_original_nonstart_seals_owner_and_retains_exact_proof(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with owned_task(node_path, monkeypatch) as (c, r):

        def cancelled(*args: object, **kwargs: object) -> tuple[()]:
            raise PermissionError("Explicit unit cancellation before original acquire")

        monkeypatch.setattr(c.bundle.preparation, "acquire", cancelled)
        with pytest.raises(TaskExecutionUnconfirmed) as failed:
            c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
        assert isinstance(failed.value.primary, PermissionError)
        closed = c.bundle.finalization.state.closed
        assert closed is not None
        assert r.browser_owner.sealed and closed.closures[0].status == "closed"
        # No prepare was confirmed: no restore/safe Reset may be fabricated.
        assert c.bundle.finalization.state.reset is None
        op = c.p.plan.operation.cleanup(
            "unit-read-original-nonstart",
            now=c.p.original.resource.clock.utcnow(),
            seconds=30,
        )
        r.verify_closed(c.p.plan, closed, op, c.p.original.resource.controls.bind(op))
        with pytest.raises(OwnershipConflict):
            r.browser_owner.begin()
        assert c.native.loader.session.calls == 0


@pytest.mark.parametrize("value", [None, "browser", 0, {}, []])
def test_browser_holder_rejects_wrong_type_without_consuming_factory(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, value: Any
) -> None:
    with owned_task(node_path, monkeypatch) as (_, r):
        h = r.browser_owner
        h.begin()
        with pytest.raises(TypeError):
            h.retain(value)
        assert h.constructing and h.original() is None and not h.sealed
        with pytest.raises(OwnershipConflict):
            h.seal_unstarted()
