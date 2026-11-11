"""Bind a sealed shared Actor journal to every original Map browser return."""

from lab_generate_skill.policies.sealed_browser_trace import (
    require_original_sealed_browser_trace,
    require_original_browser_actor_request,
)
from lab_generate_skill.domain.actor_run import ActorRunRequest, ActorStop
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    IncompleteAnswerEvidence,
)
from lab_generate_skill.ports.evaluation_evidence import (
    EvaluationEvidenceReader,
    TraceAnswerReader,
)
from lab_generate_skill.ports.map_terminal import OriginalMapTerminal
from lab_generate_skill.domain.evidence import EvidenceRef
from .page_health import MapPageHealth


def sealed_browser_trace(
    trace_ref: EvidenceRef,
    snapshot_ref: EvidenceRef,
    terminal: OriginalMapTerminal,
    page: MapPageHealth,
    reads: EvaluationEvidenceReader,
    answer_reader: TraceAnswerReader,
) -> tuple[InteractionTrace, tuple[BrowserReadout, ...]]:
    trace = reads.read(
        trace_ref,
        "interaction-trace/1",
        InteractionTrace,
        limit=16 * 1024 * 1024,
    )
    journal = reads.read(
        snapshot_ref,
        "trace-journal-snapshot/1",
        TraceSnapshot,
        limit=16 * 1024 * 1024,
    )
    initial, browser = terminal.initial, terminal.initial.browser
    plan = journal.plan
    run = reads.read(plan.binding.run.plan_ref, "run-plan/3", RunPlan)
    require_original_sealed_browser_trace(run, journal, trace, initial)
    stop = reads.read(trace.stop_evidence_ref, "trace-stop/1", ActorStop)
    request = reads.read(
        stop.request_ref, stop.request_ref.content_schema, ActorRunRequest
    )
    if request.schema_version != stop.request_ref.content_schema:
        raise EvidenceIntegrityError(
            "Map Actor request schema differs from original reference"
        )
    require_original_browser_actor_request(journal, trace, initial, stop, request)
    answer_reader(trace, initial.prepared.public_task, reads)
    originals = [initial.returned]
    for turn in trace.turns:
        if turn.interaction is not None:
            event = turn.interaction
            browser.check_operation(event.operation, "execute")
            if event.result is None:
                raise IncompleteAnswerEvidence("Original Map action return missing")
            originals.append(
                reads.read(
                    event.result.return_ref, "browser-step-return/1", BrowserReadout
                )
            )
    final = reads.read(
        trace.final_observation_ref, "observation/1", Observation, public=True
    )
    if final != terminal.readout.observation:
        raise EvidenceIntegrityError(
            "Map terminal changed original final public observation"
        )
    urls = [t.url for t in final.tabs if t.tab_id == final.active_tab_id]
    if len(urls) != 1 or (
        page.status_source != "document_changed" and page.url != urls[0]
    ):
        raise EvidenceIntegrityError(
            "Map health changed original active terminal document"
        )
    if originals[-1] != terminal.readout:
        raise EvidenceIntegrityError(
            "Original terminal differs from final Actor return"
        )
    return trace, tuple(originals)
