"""Close the exact acquired browser even when evidence or bookkeeping fails.

A clean ledger state requires explicit complete-resource authority evidence.
An uncertain start/closure stays quarantined; primary and all cleanup failures
survive. Only this original channel is aborted, never a replacement resource.
"""

from dataclasses import asdict
from datetime import datetime, timezone
from lab_generate_skill.domain.browser_resource import (
    BrowserResourceSpec,
    BrowserResourceAttempt,
)
from lab_generate_skill.domain.lifecycle import (
    OperationContext,
    ClosureReceipt,
    ResourceState,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import ResourceJournal, OperationControls, Clock
from lab_generate_skill.ports.browser_resources import BrowserResourceAuthority
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from .worker_client import SupervisedBrowserSession
from . import step as step_runtime
from .step_records import diagnostic_candidates, save
from .worker_protocol import BrowserWorkerReply
from .resource_records import phase, fact, acknowledged


def close_browser_resource(
    spec: BrowserResourceSpec,
    client: SupervisedBrowserSession,
    attempt: BrowserResourceAttempt,
    acquisition: OperationContext,
    intent_ref: EvidenceRef,
    *,
    journal: ResourceJournal,
    evidence: EvidenceStore,
    controls: OperationControls,
    clock: Clock,
    authority: BrowserResourceAuthority,
    primary: BaseException | None,
    startup_reply: BrowserWorkerReply | None,
    initial_ready_ref: EvidenceRef | None,
    step: step_runtime.BrowserStepState,
    cleanup_seconds: int = 30,
) -> None:
    errors: list[BaseException] = []
    record = None
    cleanup = None
    closure = None
    ending_ref = None
    step_closed = None
    process_stop = None
    try:
        if type(cleanup_seconds) is not int or not 1 <= cleanup_seconds <= 3600:
            raise ValueError(
                "Explicit bounded browser metadata cleanup duration required"
            )
        cleanup = acquisition.cleanup(
            phase(acquisition, "cleanup").operation_id,
            now=clock.utcnow(),
            seconds=cleanup_seconds,
        )
        record = journal.read(spec.token, phase(cleanup, "inspect"))
        if (
            record.token != spec.token
            or len(record.events) < 2
            or record.events[1].operation != acquisition
            or record.events[1].evidence != (intent_ref,)
            or record.state not in ("acquiring", "acquired", "closing")
        ):
            raise OwnershipConflict(
                "Cleanup cannot change another or finished acquisition"
            )
        if record.state != "closing":
            op = phase(cleanup, "closing")
            ref = fact(evidence, spec, op, "closing", {}, controls.bind(cleanup))
            record = acknowledged(
                journal.advance(spec.token, "closing", (ref,), record.revision, op),
                spec,
                "closing",
                op,
                ref,
                record.revision + 1,
            )
    except BaseException as error:
        errors.append(error)
    # Physical shutdown gets its own original-scope guard even if the injected
    # bookkeeping clock or persistence has failed. Never depend on clean marking.
    try:
        physical = acquisition.cleanup(
            phase(acquisition, "physical-close").operation_id,
            now=datetime.now(timezone.utc),
            seconds=10,
        )
        # Admission may read persistent ownership. The channel itself starts its
        # separate short stop budget only after that mandatory current check.
        if cleanup is not None:
            physical = physical.model_copy(update={"deadline": cleanup.deadline})
        client.close(
            physical,
            control=(
                controls.bind(physical)
                if cleanup is not None
                else DeadlineControl(10, physical.operation_id)
            ),
        )
    except BaseException as error:
        errors.append(error)
        try:
            client.channel.abort(DeadlineControl(5, "browser-emergency-abort"))
        except BaseException as emergency:
            errors.append(emergency)
    capture = client.channel.capture
    stop_control = DeadlineControl(15, "browser-original-step-close")
    if step.processes is not None:
        try:
            step.processes.stop(stop_control)
        except BaseException as error:
            errors.append(error)
        finally:
            process_stop = step.processes.facts
    try:
        step_closed = step_runtime.observe_closed(
            spec,
            step,
            capture.termination,
            evidence,
            stop_control,
            metadata_control=(
                controls.bind(cleanup)
                if cleanup is not None
                else DeadlineControl(5, "browser-failed-clock-diagnostic")
            ),
        )
        if step_closed is not None and step_closed.target != attempt.target:
            raise OwnershipConflict(
                "Browser step closure changed original attempt target"
            )
    except BaseException as error:
        errors.append(error)
    finally:
        if step.processes is not None:
            processes, step.processes = step.processes, None
            try:
                processes.close()
            except BaseException as error:
                errors.append(error)
        if step.pin is not None:
            pinned, step.pin = step.pin, None
            try:
                pinned.close()
            except BaseException as error:
                errors.append(error)
    capture_ref = None
    try:
        capture_ref = save(
            evidence,
            attempt.target,
            "worker-capture",
            [],
            [capture],
            (
                controls.bind(cleanup)
                if cleanup is not None
                else DeadlineControl(5, "browser-worker-diagnostic")
            ),
            primary,
        )
    except BaseException as error:
        errors.append(error)
    try:
        if cleanup is None:
            raise OwnershipConflict("No bookkeeping cleanup context")
        returned = authority.verify_closed(
            spec,
            attempt,
            capture.termination,
            step_closed,
            cleanup,
            controls.bind(cleanup),
        )
        closure = ClosureReceipt.model_validate(returned)
        if (
            closure.token != spec.token
            or closure.operation_id != cleanup.operation_id
            or closure.status != "closed"
            or closure.primary_error is not None
        ):
            raise OwnershipConflict(
                "Browser complete-resource closure remains unconfirmed"
            )
        for ref in closure.evidence:
            if ref.visibility != "private":
                raise OwnershipConflict("Browser closure facts must be private")
            evidence.read(ref, control=controls.bind(cleanup))
        if (
            capture.termination is None
            or capture.termination.state == "unconfirmed"
            or capture.termination.cleanup_errors
        ):
            raise OwnershipConflict("Browser channel termination remains unconfirmed")
        if capture.termination.process_id != attempt.launcher_pid:
            raise OwnershipConflict("Browser termination changed original launcher")
    except BaseException as error:
        errors.append(error)
    try:
        if cleanup is None:
            raise OwnershipConflict("Cannot publish cleanup without its context")
        op = phase(cleanup, "ended")
        state: ResourceState = "quarantined" if errors else "closed"
        ending_ref = fact(
            evidence,
            spec,
            op,
            state,
            {
                "attempt": attempt.model_dump(mode="json"),
                "initial_ready_ref": (
                    None
                    if initial_ready_ref is None
                    else initial_ready_ref.model_dump(mode="json")
                ),
                "process_stop": (
                    None
                    if process_stop is None
                    else process_stop.model_dump(mode="json")
                ),
                "step_closed": (
                    None if step_closed is None else step_closed.model_dump(mode="json")
                ),
                "closure": None if closure is None else closure.model_dump(mode="json"),
                "termination": (
                    None if capture.termination is None else asdict(capture.termination)
                ),
                "startup_reply": (
                    None
                    if startup_reply is None
                    else startup_reply.model_dump(mode="json")
                ),
                "configuration_reply": (
                    None
                    if client.configuration_reply is None
                    else client.configuration_reply.model_dump(mode="json")
                ),
                "worker_capture_ref": (
                    None if capture_ref is None else capture_ref.model_dump(mode="json")
                ),
                "last_readout": (
                    None
                    if client.last_readout is None
                    else client.last_readout.model_dump(mode="json")
                ),
                "last_reply": (
                    None
                    if client.last_reply is None
                    else client.last_reply.model_dump(mode="json")
                ),
                "primary": (
                    None
                    if primary is None
                    else describe_error(primary).model_dump(mode="json")
                ),
                "step_diagnostic_candidates": [
                    ref.model_dump(mode="json")
                    for ref in diagnostic_candidates(
                        ([primary] if primary is not None else []) + errors
                    )
                ],
                "cleanup_errors": [
                    describe_error(e).model_dump(mode="json") for e in errors
                ],
            },
            controls.bind(cleanup),
        )
        if record is None or record.state != "closing":
            raise OwnershipConflict(
                "Closing unconfirmed; retain ending fact for reconciliation"
            )
        acknowledged(
            journal.advance(spec.token, state, (ending_ref,), record.revision, op),
            spec,
            state,
            op,
            ending_ref,
            record.revision + 1,
        )
    except BaseException as error:
        errors.append(error)
    if primary is not None:
        setattr(primary, "command_capture", capture)
        setattr(primary, "browser_resource_ending_ref", ending_ref)
        setattr(primary, "browser_resource_startup_reply", startup_reply)
        setattr(primary, "browser_resource_readout", client.last_readout)
        setattr(primary, "browser_resource_initial_ready_ref", initial_ready_ref)
    if errors:
        result = BaseExceptionGroup(
            "Browser resource and cleanup failed",
            ([primary] if primary is not None else []) + errors,
        )
        setattr(result, "command_capture", capture)
        setattr(result, "browser_resource_ending_ref", ending_ref)
        setattr(result, "browser_resource_startup_reply", startup_reply)
        setattr(result, "browser_resource_readout", client.last_readout)
        setattr(result, "browser_resource_initial_ready_ref", initial_ready_ref)
        raise result from None
