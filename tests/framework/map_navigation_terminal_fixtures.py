"""Current Task/unique0/Actor-loop/terminal full-chain software fixture.

The original runner, journals, frames and CAS run. Model/Page/kernel/source are
explicit doubles; a positive control is not a real Actor result or training data.
"""

from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import pytest
from lab_generate_skill.bootstrap.map_navigation_terminal import (
    read_map_navigation_terminal,
)
from lab_generate_skill.bootstrap.map_overlay_records import map_original_state_reader
from lab_generate_skill.adapters.sites.recorded_capture import RecordedSiteCapture
from lab_generate_skill.domain.map_navigation_terminal import (
    MapNavigationTerminalSelection,
)
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.baseline import BaselineInputs
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.sites.map.evidence_schema import MapCapturePair
from lab_generate_skill.sites.map.navigation_terminal_evidence import (
    NavigationTerminalEvidence,
)
from lab_generate_skill.sites.map.tasks.overlay_environment import (
    OverlayEnvironmentChecks,
)
from lab_generate_skill.sites.map.evaluation_guard import complete_final_guard
from map_navigation_prepared_fixtures import NavigationPreparedCase
from map_navigation_initial_fixtures import initial_navigation, NavigationInitialCase
from map_navigation_browser_fixtures import Page
from map_navigation_group_cases import MEMBERS
from map_qualification_fixtures import qualified, QualifiedMapCase
from map_registered_worker_fixtures import RegisteredMapCase
from map_actor_trace_fixtures import execute_browser_actor
from map_ready_baseline_fixtures import ready_initial_baseline
from map_browser_capture_native import capture
from preparation_record_fixtures import put
from test_site_capture import Authority
from test_slurm_commands import guard


@dataclass
class NavigationTerminalCase:
    original: RegisteredMapCase
    qualified: QualifiedMapCase
    initial: NavigationInitialCase
    selection: MapNavigationTerminalSelection
    selection_ref: EvidenceRef
    trace: InteractionTrace
    closure: ClosureReceipt
    closure_ref: EvidenceRef
    final_guard: MapCapturePair
    read_operation: OperationContext
    baseline_inputs: BaselineInputs
    baseline_ref: EvidenceRef

    def load(self) -> NavigationTerminalEvidence:
        c = self.original
        c.observer = "controller"
        return read_map_navigation_terminal(
            c.resource.evidence,
            self.qualified.preparation.records,
            self.selection_ref,
            self.read_operation,
            guard(60),
        )

    def check_guard(self, terminal: NavigationTerminalEvidence) -> None:
        c = self.original
        states = OverlayEnvironmentChecks(
            c.resource.evidence,
            map_original_state_reader(
                c.configuration, self.qualified.live.site.instance
            ),
            c.resource.spec,
            self.qualified.live.site,
        )
        environment = states._environment(self.qualified.environment, guard(60))
        assert self.qualified.environment.snapshot_ref is not None
        complete_final_guard(
            self.final_guard,
            self.closure,
            terminal,
            environment,
            states,
            self.qualified.environment.snapshot_ref,
            guard(60),
        )


@contextmanager
def terminal_navigation(
    c: RegisteredMapCase, patch: pytest.MonkeyPatch, *, negative: bool = False
) -> Iterator[NavigationTerminalCase]:
    source = c.scope.task.source_task_id
    row = next(row for row in MEMBERS if row[0] == source)
    target, heading = row[1:]
    if negative:
        target, heading = "/about", "Wrong named document"

    def effect(page: Page, payload: str) -> None:
        assert payload == "click('a')"
        origin = page.url.split("/", 3)[:3]
        page.url = "/".join(origin) + target
        page.headings = [heading]

    with qualified(c, patch) as q:
        p = q.preparation
        assert isinstance(p, NavigationPreparedCase)
        with initial_navigation(
            c,
            q,
            patch,
            public_text="RootWebArea 'Map navigation'\n  [a] link 'Requested local document'",
            step_effect=effect,
        ) as n:
            inputs, baseline = ready_initial_baseline(
                c, p, n.records, n.selection, n.operation
            )
            first = n.engine.last_readout
            initial_ref = n.records.publish(n.selection, n.operation)
            trace_ref, snapshot_ref, trace, snapshot = execute_browser_actor(
                c, n.browser, n.session
            )
            assert trace.interactions == trace.generations == 1
            pair = capture(n.browser, n.session, "map-navigation-page-health")
            returned = trace.turns[-1].interaction
            assert returned is not None and returned.result is not None
            selection = MapNavigationTerminalSelection(
                initial=n.selection,
                initial_evidence=n.evidence,
                initial_checks_ref=initial_ref,
                terminal_return_ref=returned.result.return_ref,
                capture_intent_ref=pair.intent_ref,
                capture_result_ref=pair.result_ref,
                trace_ref=trace_ref,
                trace_snapshot_ref=snapshot_ref,
            )
            selected_ref = put(c.resource.evidence, selection)
            assert first is not None and first.observation.sequence == 0
            assert n.calls.count("project") == 2 and n.calls.count("actual_action") == 1
        store = c.resource.evidence
        br = n.browser.journal.read(n.browser.spec.token, n.browser.op)
        assert br.state == "closed"
        ending = json.loads(store.read(br.events[-1].evidence[0]))
        closure = ClosureReceipt.model_validate_json(
            json.dumps(ending["details"]["closure"])
        )
        closure_ref = put(store, closure)
        c.observer = "worker"
        inspection = c.request("inspect", "navigation-final-whole-guard")
        inspection = inspection.model_copy(
            update={
                "operation": inspection.operation.model_copy(
                    update={"parent_operation_id": closure.operation_id}
                )
            }
        )
        recorder = RecordedSiteCapture(q.live.capture, store, Authority(store))
        result = recorder.capture(
            SiteCaptureRequest(
                inspection=inspection,
                collector_id="map-navigation-state",
                collector_version="1",
            ),
            control=guard(60),
        )
        assert recorder.intent_ref is not None
        final_guard = MapCapturePair(intent_ref=recorder.intent_ref, result_ref=result)
        c.observer = "controller"
        yield NavigationTerminalCase(
            c,
            q,
            n,
            selection,
            selected_ref,
            trace,
            closure,
            closure_ref,
            final_guard,
            n.operation.cleanup(
                "navigation-terminal-read", now=datetime.now(timezone.utc), seconds=60
            ),
            inputs,
            baseline,
        )
