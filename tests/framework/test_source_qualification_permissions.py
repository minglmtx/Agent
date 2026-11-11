"""Source-only effect boundaries; native/kernel premises explicitly synthetic."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.adapters.sites.source_qualification_authority import (
    SourceQualificationSiteAuthority,
)
from lab_generate_skill.adapters.browsergym.source_qualification_authority import (
    SourceQualificationBrowserAuthority,
)
from lab_generate_skill.adapters.sites.task_initialization import (
    RecordedTaskInitialization,
)
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.domain.browser_resource import BrowserResourceAttempt
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.site_resource import SiteResourceAttempt
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from task_resource_owner_fixtures import owned_task
from site_instance_fixtures import node_path as node_path


def test_source_permissions_one_initial_no_actions_no_actor_and_unknown_close(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with owned_task(node_path, monkeypatch) as (c, r):
        inputs = r.site.spec.configuration.map_inputs
        assert inputs is not None

        class UnitSourceOwner(OriginalSourceQualificationOwner):
            def require_caller(
                self, op: OperationContext, control: OperationControl
            ) -> None:
                r.owner.caller(op, control)

        owner = UnitSourceOwner(
            inputs.scope,
            r.site.spec.slurm.execution,
            r.site.spec.slurm.parent,
            r.owner.evidence,
        )
        site = SourceQualificationSiteAuthority(owner, r.site.spec, r.site.operation)
        control = c.p.original.resource.controls.bind(r.site.operation)
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pytest.raises(OwnershipConflict):
                pool.submit(
                    site.authorize_spawn, r.site.spec, r.site.operation, control
                ).result()
        assert not site._spawn
        site.authorize_spawn(r.site.spec, r.site.operation, control)
        with pytest.raises(OwnershipConflict):
            site.authorize_spawn(r.site.spec, r.site.operation, control)
        site.verify(r.site.spec.configuration, "configure", r.site.operation, control)
        with pytest.raises(OwnershipConflict):
            site.verify(
                r.site.spec.configuration, "configure", r.site.operation, control
            )
        cleanup = r.site.operation.cleanup(
            "source-site-close", now=r.site.operation.deadline, seconds=30
        )
        with pytest.raises(OwnershipConflict, match="unconfirmed"):
            site.verify_closed(
                r.site.spec,
                SiteResourceAttempt(spawn_attempted=False),
                None,
                None,
                cleanup,
                c.p.original.resource.controls.bind(cleanup),
            )
        assert c.native.loader.session.calls == 0 and c.p.requests == []
        original = c.bundle.initialization.factory
        checked: list[bool] = []

        def factory(
            plan: TaskExecutionPlan, op: OperationContext, read: OperationControl
        ) -> RecordedTaskInitialization:
            current = original(plan, op, read)
            browser = r.browser()
            assert browser is not None and browser.phase == "new"
            b = SourceQualificationBrowserAuthority(
                owner, browser.spec, browser.operation
            )
            bound = c.p.original.resource.controls.bind(browser.operation)
            with pytest.raises(OwnershipConflict):
                b.verify(
                    browser.spec.configuration.spec,
                    "start",
                    None,
                    browser.operation,
                    bound,
                )
            b.authorize_start(browser.spec, browser.operation, bound)
            with pytest.raises(OwnershipConflict):
                b.authorize_start(browser.spec, browser.operation, bound)
            b.verify(
                browser.spec.configuration.spec, "start", None, browser.operation, bound
            )
            b.verify(
                browser.spec.configuration.spec, "start", None, browser.operation, bound
            )
            with pytest.raises(OwnershipConflict, match="one-shot"):
                b.verify(
                    browser.spec.configuration.spec,
                    "start",
                    None,
                    browser.operation.model_copy(
                        update={"operation_id": "other-source-start"}
                    ),
                    bound,
                )
            with pytest.raises(OwnershipConflict, match="cannot dispatch"):
                b.verify(
                    browser.spec.configuration.spec,
                    "step",
                    None,
                    browser.operation,
                    bound,
                )
            close = browser.operation.cleanup(
                "source-browser-close", now=op.deadline, seconds=30
            )
            with pytest.raises(OwnershipConflict, match="unconfirmed"):
                b.verify_closed(
                    browser.spec,
                    BrowserResourceAttempt(start_attempted=False),
                    None,
                    None,
                    close,
                    c.p.original.resource.controls.bind(close),
                )
            checked.append(True)
            raise PermissionError(
                "Explicit source-only probe cancels before any browser/model effect"
            )

        monkeypatch.setattr(c.bundle.initialization, "factory", factory)
        with pytest.raises(TaskExecutionUnconfirmed):
            c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
        assert checked == [True] and c.native.loader.session.calls == 0
