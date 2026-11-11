"""Real wire/CAS/shared Actor journal with explicit native/model/page doubles.

Both retained Actor1 and current Actor2/context exercise the readonly terminal
proof. Full default capture/guard/owned execution is checked independently.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pytest
import browser_resource_fixtures
from browser_worker_fixtures import UnitBrowser
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.admin_navigation_browser_initialization import (
    AdminNavigationInitialization,
)
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureRequest,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.browsergym.recorded_capture import (
    RecordedBrowserCapture,
)
from lab_generate_skill.adapters.browsergym.worker_client import (
    SupervisedBrowserSession,
)
from lab_generate_skill.sites.shopping_admin.navigation_terminal_schema import (
    AdminNavigationTerminalSelection,
)
from lab_generate_skill.sites.shopping_admin.evidence_schema import AdminNavigationPage
from lab_generate_skill.evaluators.shopping_admin.navigation import REQUIREMENTS
from evidence_control_fixtures import EvidenceFixtureStore
from site_resource_fixtures import Case as SiteCase
from admin_navigation_initial_fixtures import initial_case
from map_actor_trace_fixtures import execute_browser_actor
from preparation_record_fixtures import put
from test_browser_capture import Authority
from test_slurm_commands import guard


@dataclass
class ActorCase:
    resource: SiteCase
    scope: StateScope
    workspace: Path
    binding: EvidenceRef


def install_navigation_browser(
    patch: pytest.MonkeyPatch, native: Any, negative: bool
) -> None:
    class NavigationBrowser(UnitBrowser):
        def __init__(self, configuration: BrowserWorkerConfiguration) -> None:
            super().__init__(configuration)
            self.last_capture: BrowserCaptureResult | None = None

        def value(
            self, op: OperationContext, action: BrowserAction | None
        ) -> BrowserReadout:
            old = super().value(op, action)
            if action is not None:
                actual_target = (
                    "/".join(self.spec.task.start_url.split("/", 3)[:3])
                    + "/admin"
                    + ("/wrong" if negative else native["spec"]["target_path"])
                )
                old = old.model_copy(
                    update={
                        "observation": old.observation.model_copy(
                            update={
                                "tabs": (
                                    old.observation.tabs[0].model_copy(
                                        update={"url": actual_target}
                                    ),
                                )
                            }
                        )
                    }
                )
            self.last_readout = old
            return old

        def capture_page(
            self, request: BrowserCaptureRequest, *, control: OperationControl
        ) -> BrowserCaptureResult:
            control.checkpoint()
            assert self.last_readout is not None
            request.check_readout(self.spec, self.last_readout)
            current = self.last_readout.observation
            page = AdminNavigationPage(
                url=current.tabs[0].url,
                heading=(
                    "Initial catalog"
                    if current.sequence == 0
                    else "Wrong" if negative else native["spec"]["heading"]
                ),
                login=False,
                page_error=False,
            )
            self.last_capture = BrowserCaptureResult(
                request_sha256=request.digest,
                captured_at=datetime.now(timezone.utc),
                private_result=page.model_dump_json(),
            )
            return self.last_capture

    patch.setattr(browser_resource_fixtures, "UnitBrowser", NavigationBrowser)


@contextmanager
def terminal_case(
    root: Path,
    patch: pytest.MonkeyPatch,
    contracts: Any,
    *,
    negative: bool = False,
    current: bool = False,
) -> Iterator[Any]:
    native = contracts[0][0]

    install_navigation_browser(patch, native, negative)
    with initial_case(root, patch, contracts) as c:
        p, b, session = c.prepared, c.prepared.browser, c.session
        store: EvidenceFixtureStore = b.evidence
        initial = c.records.reader.load(c.selection, c.op, guard(30))
        first = c.records.publish(c.selection, c.op)
        contract = TaskBinding.model_validate_json(
            store.read(initial.prepared.task_binding_ref)
        )
        evaluation = EvaluationContract(
            identity=contract.identity,
            attempt_id=initial.prepared.scope.attempt_id,
            task_contract_ref=initial.prepared.task_binding_ref,
            public_task_ref=contract.public_task_ref,
            completion_spec_ref=contract.private_spec_ref,
            requirements=REQUIREMENTS,
            scope="engineering",
        )

        def page_capture(name: str) -> tuple[EvidenceRef, EvidenceRef]:
            assert session.observation_ref is not None
            operation = b.op.model_copy(update={"operation_id": name})
            request = BrowserCaptureRequest(
                scope=initial.prepared.scope,
                operation=operation,
                observation_sha256=session.observation_ref.sha256,
                collector_id="admin-navigation-page",
                collector_version="1",
            )
            assert isinstance(session.engine, SupervisedBrowserSession)
            capture = RecordedBrowserCapture(session.engine, store, Authority(store))
            result = capture.capture(request, control=b.controls.bind(operation))
            assert capture.intent_ref is not None
            return capture.intent_ref, result

        initial_intent, initial_result = page_capture("initial-page")
        case = ActorCase(
            p.site, initial.prepared.scope, root, initial.prepared.task_binding_ref
        )
        if current:
            from admin_navigation_actor_fixtures import current_actor
            from task_capture_actor_fixtures import controlled_context

            request, binding = current_actor(case, b, session, store)
            trace_ref, snapshot_ref, trace, snapshot = execute_browser_actor(
                case,
                b,
                session,
                request=request,
                binding=binding,
                context_factory=lambda r, j: controlled_context(r, j, store),
            )
        else:
            trace_ref, snapshot_ref, trace, snapshot = execute_browser_actor(
                case, b, session
            )
        final_intent, final_result = page_capture("final-page")
        interaction = trace.turns[-1].interaction
        assert interaction is not None and interaction.result is not None
        assert isinstance(
            initial.browser.configuration.initialization, AdminNavigationInitialization
        )
        assert p.preparation.request.snapshot_ref is not None
        environment = EnvironmentSelection(
            scope=initial.prepared.scope,
            spec_ref=initial.prepared.spec_ref,
            site_spec_ref=put(store, p.site.spec),
            site_started_ref=initial.browser.configuration.initialization.site_ref,
            snapshot_ref=p.preparation.request.snapshot_ref,
        )
        selected = AdminNavigationTerminalSelection(
            scope=initial.prepared.scope,
            initial=c.selection,
            initial_checks_ref=first,
            initial_capture_intent_ref=initial_intent,
            initial_capture_result_ref=initial_result,
            trace_ref=trace_ref,
            trace_snapshot_ref=snapshot_ref,
            terminal_return_ref=interaction.result.return_ref,
            page_intent_ref=final_intent,
            page_result_ref=final_result,
            prepare_request_ref=p.preparation.selection.request_ref,
            environment_selection_ref=put(store, environment),
        )
        from types import SimpleNamespace

        yield SimpleNamespace(
            store=store,
            preparations=p.preparation.adapter,
            selection=selected,
            reference=put(store, selected),
            contract=evaluation,
            operation=c.op,
            browser=b,
            snapshot=snapshot,
            initial=initial,
        )
