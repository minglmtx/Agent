"""Selected8 terminal/trace/whole guard composition; effects explicitly simulated."""

from pathlib import Path
from datetime import datetime, timezone
import pytest
from lab_generate_skill.bootstrap.map_navigation_terminal import (
    read_map_navigation_terminal,
)
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.map_navigation_browser_initialization import (
    MapNavigationInitialization,
)
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.sites.map.navigation_rules import navigation_outcome
from lab_generate_skill.sites.map.navigation_page_schema import NavigationPageHealth
from lab_generate_skill.sites.map.tasks.navigation_spec import NavigationSpec
from map_navigation_terminal_fixtures import terminal_navigation
from map_navigation_browser_fixtures import CancelledControl
from map_navigation_group_cases import SOURCES
from map_registered_worker_fixtures import RegisteredMapCase
from map_qualification_fixtures import restore
from preparation_record_fixtures import put
from site_instance_fixtures import node_path as node_path
from test_site_resource import inspect
from test_slurm_commands import guard


@pytest.mark.parametrize("source", SOURCES)
def test_each_member_current_actor_loop_terminal_trace_full_guard_original_rule_and_reset(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=source)
    try:
        with terminal_navigation(c, monkeypatch) as t:
            before = (
                list(t.initial.calls),
                list(t.initial.page.calls),
                len(c.sql.calls),
            )
            terminal = t.load()
            t.check_guard(terminal)
            assert isinstance(c.private, NavigationSpec)
            init = terminal.initial.browser.configuration.initialization
            assert isinstance(init, MapNavigationInitialization)
            outcome = navigation_outcome(
                c.private,
                terminal.page.original_page(),
                site_origin=init.endpoint.rstrip("/"),
                runtime_error=False,
                selected_records_unchanged=True,
            )
            assert outcome.status == "success" and outcome.reward == 1
            assert t.load() == terminal
            assert (t.initial.calls, t.initial.page.calls, len(c.sql.calls)) == before
            assert c.worker is not None and c.worker.references is None
            reset = restore(t.qualified, closure_refs=(t.closure_ref,))
            checks = t.qualified.qualifications.checks.reset(
                reset, put(c.resource.evidence, reset), guard(60)
            )
            assert (
                checks.task.status
                == checks.environment.status
                == checks.health.status
                == "pass"
            )
        assert inspect(c.resource).state == "closed"
    finally:
        c.close_sockets()


def test_healthy_wrong_goal_is_original_failure_and_can_reset(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=SOURCES[0])
    try:
        with terminal_navigation(c, monkeypatch, negative=True) as t:
            terminal = t.load()
            t.check_guard(terminal)
            assert isinstance(c.private, NavigationSpec)
            init = t.initial.browser.spec.configuration.initialization
            assert isinstance(init, MapNavigationInitialization)
            assert (
                navigation_outcome(
                    c.private,
                    terminal.page.original_page(),
                    site_origin=init.endpoint.rstrip("/"),
                    runtime_error=False,
                    selected_records_unchanged=True,
                ).status
                == "failure"
            )
            reset = restore(t.qualified, closure_refs=(t.closure_ref,))
            assert (
                t.qualified.qualifications.checks.reset(
                    reset, put(c.resource.evidence, reset), guard(60)
                ).health.status
                == "pass"
            )
    finally:
        c.close_sockets()


def test_terminal_binding_faults_cannot_invent_known_execution_or_dispatch_again(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=SOURCES[0])
    try:
        with terminal_navigation(c, monkeypatch) as t:
            store = c.resource.evidence
            original = t.selection
            good = t.load()
            before = (
                list(t.initial.calls),
                list(t.initial.page.calls),
                len(c.sql.calls),
            )
            intent = BrowserCaptureIntent.model_validate_json(
                store.read(original.capture_intent_ref)
            )
            result = BrowserCaptureResult.model_validate_json(
                store.read(original.capture_result_ref)
            )
            variants = [
                original.model_copy(
                    update={
                        "terminal_return_ref": good.initial.acquired.details.started.initial_return_ref
                    }
                ),
                original.model_copy(
                    update={
                        "capture_intent_ref": put(
                            store,
                            intent.model_copy(
                                update={"configuration_sha256": "f" * 64}
                            ),
                        )
                    }
                ),
                original.model_copy(
                    update={
                        "capture_result_ref": put(
                            store,
                            result.model_copy(update={"request_sha256": "f" * 64}),
                        )
                    }
                ),
            ]
            snap = TraceSnapshot.model_validate_json(
                store.read(original.trace_snapshot_ref)
            )
            bad_plan = snap.plan.model_copy(
                update={"initial_observation_ref": t.trace.final_observation_ref}
            )
            variants.append(
                original.model_copy(
                    update={
                        "trace_snapshot_ref": put(
                            store, snap.model_copy(update={"plan": bad_plan})
                        )
                    }
                )
            )
            op = t.initial.operation.cleanup(
                "bad-navigation-terminal",
                now=datetime.now(timezone.utc),
                seconds=30,
            )
            expected = (
                "Capture changed original browser or latest observation",
                "Navigation terminal capture changed original return/configuration/operation",
                "Navigation terminal capture changed original return/configuration/operation",
                "Generation intent changed original scope or observation",
            )
            for selection, message in zip(variants, expected, strict=True):
                with pytest.raises(OwnershipConflict, match="^" + message + "$"):
                    read_map_navigation_terminal(
                        store,
                        t.qualified.preparation.records,
                        put(store, selection),
                        op,
                        guard(30),
                    )
            with pytest.raises(OperationStopped):
                read_map_navigation_terminal(
                    store,
                    t.qualified.preparation.records,
                    t.selection_ref,
                    op,
                    CancelledControl(),
                )
            assert (t.initial.calls, t.initial.page.calls, len(c.sql.calls)) == before
    finally:
        c.close_sockets()
