"""Real supplier state gates, explicit synthetic resources and permission edges."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.adapters.models.claimed_resource_authority import (
    ClaimedActorResourceAuthority,
)
from lab_generate_skill.adapters.browsergym.claimed_authority import (
    ClaimedBrowserResourceAuthority,
)
from lab_generate_skill.domain.actor_step import ActorStepCleanup
from lab_generate_skill.domain.browser_step import BrowserSlurmBinding
from lab_generate_skill.domain.browser_resource import (
    BrowserResourceSpec,
    BrowserResourceAttempt,
)
from lab_generate_skill.domain.process_identity import ProcessTermination
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.adapters.sites.task_initialization import (
    RecordedTaskInitialization,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from task_resource_owner_fixtures import owned_task
from browser_resource_fixtures import resource_case
from site_instance_fixtures import node_path as node_path
import lab_generate_skill.adapters.models.claimed_resource_authority as actor_module


def test_actor_supplier_one_start_original_caller_and_cleanup_observation_after_bookkeeping_failure(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with owned_task(node_path, monkeypatch) as (c, r):
        spec, op = r.model.spec, c.native.actor.op
        calls: list[bool] = []
        denied = False

        def model(
            value: object,
            command: OperationContext,
            control: OperationControl,
            *,
            new_work: bool,
        ) -> None:
            control.checkpoint()
            assert value == spec
            calls.append(new_work)
            if denied:
                raise PermissionError("Explicit unit revoked metadata permission")

        monkeypatch.setattr(r.owner, "model", model)
        a = ClaimedActorResourceAuthority(r.owner, spec, op)
        with a:
            control = c.p.original.resource.controls.bind(op)
            with ThreadPoolExecutor(max_workers=1) as pool:
                with pytest.raises(OwnershipConflict):
                    pool.submit(a.authorize_start, spec, op, control).result()
            assert not a.start_attempted and calls == []
            a.authorize_start(spec, op, control)
            assert calls == [True]
            with pytest.raises(OwnershipConflict):
                a.authorize_start(spec, op, control)
            denied = True
            physical: list[object] = []

            def closed(*args: Any, **kwargs: Any) -> None:
                physical.append(args[1])
                return None

            monkeypatch.setattr(actor_module, "observe_closed", closed)
            cleanup = op.cleanup(
                "original-actor-close",
                now=c.p.original.resource.clock.utcnow(),
                seconds=30,
            )
            # Resource provider retains actual pre-launch knowledge. Permission
            # bookkeeping failure must not suppress its physical observer call.
            with pytest.raises(PermissionError, match="revoked"):
                a.verify_closed(
                    spec,
                    ActorStepCleanup(start_attempted=False),
                    ProcessTermination(
                        process_id=None,
                        state="not_started",
                        returncode=None,
                        kill_requested=False,
                    ),
                    cleanup,
                    c.p.original.resource.controls.bind(cleanup),
                )
            assert len(physical) == 1 and calls == [True, False]
            with pytest.raises(OwnershipConflict):
                a.verify_closed(
                    spec,
                    ActorStepCleanup(start_attempted=False),
                    ProcessTermination(
                        process_id=None,
                        state="not_started",
                        returncode=None,
                        kill_requested=False,
                    ),
                    cleanup,
                    c.p.original.resource.controls.bind(cleanup),
                )
            assert len(physical) == 1 and c.native.loader.session.calls == 0


def test_browser_supplier_scope_revocation_and_unconfirmed_close_never_grant_a_receipt(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with owned_task(node_path, monkeypatch) as (c, r):
        original_factory = c.bundle.initialization.factory
        checked: list[bool] = []

        def factory(
            plan: TaskExecutionPlan,
            operation: OperationContext,
            control: OperationControl,
        ) -> RecordedTaskInitialization:
            initial = original_factory(plan, operation, control)
            browser, backend = r.browser(), c.handles.backend
            assert (
                browser is not None and browser.phase == "new" and backend is not None
            )
            spec, op = browser.spec, browser.operation
            before = (len(backend.resource.channels), c.native.loader.session.calls)
            a = ClaimedBrowserResourceAuthority(r.owner, spec, op)
            bound = c.p.original.resource.controls.bind(op)
            with ThreadPoolExecutor(max_workers=1) as pool:
                with pytest.raises(OwnershipConflict):
                    pool.submit(a.authorize_start, spec, op, bound).result()
            assert not a.start_attempted
            a.authorize_start(spec, op, bound)
            with pytest.raises(OwnershipConflict):
                a.authorize_start(spec, op, bound)
            a.verify(spec.configuration.spec, "start", None, op, bound)
            with pytest.raises(OwnershipConflict):
                a.verify(spec.configuration.spec, "step", None, op, bound)
            c.journals.claim_authority.denied = True
            try:
                with pytest.raises(OwnershipConflict, match="unit claim caller denied"):
                    a.verify(spec.configuration.spec, "start", None, op, bound)
            finally:
                c.journals.claim_authority.denied = False
            cleanup = op.cleanup(
                "original-browser-close",
                now=c.p.original.resource.clock.utcnow(),
                seconds=30,
            )
            with pytest.raises(OwnershipConflict, match="unconfirmed"):
                a.verify_closed(
                    spec,
                    BrowserResourceAttempt(start_attempted=False),
                    None,
                    None,
                    cleanup,
                    c.p.original.resource.controls.bind(cleanup),
                )
            assert (
                (len(backend.resource.channels), c.native.loader.session.calls)
                == before
                == (0, 0)
            )
            checked.append(True)
            return initial

        monkeypatch.setattr(c.bundle.initialization, "factory", factory)
        result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
        assert checked == [True] and result.evaluation.status == "success"
