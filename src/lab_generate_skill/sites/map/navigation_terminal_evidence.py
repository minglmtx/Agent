"""Original initial/terminal/capture/Actor trace facts, never browser execution."""

from dataclasses import dataclass
import hashlib
from lab_generate_skill.domain.map_navigation_terminal import (
    MapNavigationTerminalSelection,
)
from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.baseline import InitialStateChecks
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.map_navigation_browser_initialization import (
    MapNavigationInitialization,
)
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.evaluation_evidence import (
    EvaluationEvidenceReader,
    TraceAnswerReader,
)
from .navigation_page_schema import NavigationPageHealth
from .tasks.navigation_initial_observation import NavigationInitialObservationChecks
from .terminal_files import private_record
from .sealed_browser_trace import sealed_browser_trace


@dataclass(frozen=True)
class NavigationTerminalEvidence:
    selection: MapNavigationTerminalSelection
    initial: InitialObservationInputs
    initial_checks: InitialStateChecks
    intent: BrowserCaptureIntent
    result: BrowserCaptureResult
    readout: BrowserReadout
    page: NavigationPageHealth


def navigation_terminal_evidence(
    selection: MapNavigationTerminalSelection,
    initial: InitialObservationInputs,
    store: EvidenceReader,
    control: OperationControl,
    *,
    reads: EvaluationEvidenceReader,
    answer_reader: TraceAnswerReader,
) -> NavigationTerminalEvidence:
    selection = MapNavigationTerminalSelection.model_validate(selection)
    initial = InitialObservationInputs.model_validate(initial)
    cfg = initial.browser.configuration
    chosen = cfg.initialization
    if (
        selection.initial != initial.selection
        or not isinstance(chosen, MapNavigationInitialization)
        or cfg.map_inputs is not None
    ):
        raise OwnershipConflict(
            "Original explicit navigation initial selection required"
        )
    chosen.check(cfg.spec)
    first = private_record(
        store,
        selection.initial_checks_ref,
        "initial-state-checks/1",
        InitialStateChecks,
        control,
    )
    checks = NavigationInitialObservationChecks(
        store, selection.initial_evidence, chosen
    ).check(initial, control)
    ref = initial.acquired.details.started.initial_observation_ref
    if (
        first.scope != initial.prepared.scope
        or first.spec_ref != initial.prepared.spec_ref
        or first.prepared_ref != selection.initial.preparation.prepared_ref
        or first.observation_ref != ref
        or first.measured_state_sha256 != ref.sha256
        or first.checks != checks
        or checks.status != "pass"
        or first.operation.operation_id
        in (
            initial.returned.operation.operation_id,
            initial.acquired.operation.operation_id,
        )
    ):
        raise EvidenceIntegrityError(
            "Original navigation unique initial readiness changed"
        )
    returned = private_record(
        store,
        selection.terminal_return_ref,
        selection.terminal_return_ref.content_schema,
        BrowserReadout,
        control,
    )
    if returned.schema_version != selection.terminal_return_ref.content_schema:
        raise EvidenceIntegrityError("Original terminal return schema differs")
    initial.browser.check_operation(returned.operation, "execute")
    if returned.scope != initial.prepared.scope or (
        returned.observation.sequence == 0 and returned != initial.returned
    ):
        raise OwnershipConflict(
            "Navigation terminal return changed original scope/unique0"
        )
    intent = private_record(
        store,
        selection.capture_intent_ref,
        "browser-capture-intent/1",
        BrowserCaptureIntent,
        control,
    )
    result = private_record(
        store,
        selection.capture_result_ref,
        "browser-capture-result/1",
        BrowserCaptureResult,
        control,
    )
    request = intent.request
    initial.browser.check_operation(request.operation, "execute")
    request.check_readout(cfg.spec, returned)
    if (
        (request.collector_id, request.collector_version)
        != ("map-navigation-page-health", "1")
        or intent.configuration_sha256
        != hashlib.sha256(cfg.model_dump_json().encode()).hexdigest()
        or result.request_sha256 != request.digest
        or result.captured_at < returned.observation.captured_at
        or request.operation.operation_id
        in (
            returned.operation.operation_id,
            initial.returned.operation.operation_id,
            initial.acquired.operation.operation_id,
            initial.worker_acquired.operation.operation_id,
        )
    ):
        raise OwnershipConflict(
            "Navigation terminal capture changed original return/configuration/operation"
        )
    page = NavigationPageHealth.model_validate_json(result.private_result)
    if page.model_dump_json() != result.private_result:
        raise EvidenceIntegrityError("Noncanonical original navigation page capture")
    terminal = NavigationTerminalEvidence(
        selection, initial, first, intent, result, returned, page
    )
    trace, originals = sealed_browser_trace(
        selection.trace_ref,
        selection.trace_snapshot_ref,
        terminal,
        page.health,
        reads,
        answer_reader,
    )
    expected = initial.acquired.details.started.initial_return_ref
    for turn in reversed(trace.turns):
        if turn.interaction is not None and turn.interaction.result is not None:
            expected = turn.interaction.result.return_ref
            break
    if expected != selection.terminal_return_ref:
        raise EvidenceIntegrityError(
            "Navigation terminal reference differs from original final Actor return"
        )
    control.checkpoint()
    return terminal
