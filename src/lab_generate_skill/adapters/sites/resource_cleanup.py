"""Close the exact acquired site even when evidence or bookkeeping fails.

A clean ledger state requires explicit complete-resource authority evidence.
An uncertain start/closure stays quarantined; primary and all cleanup failures
survive. Only this original channel is aborted, never a replacement resource.
"""

from dataclasses import asdict
from datetime import datetime, timezone
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceAttempt,
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
from lab_generate_skill.ports.site_resources import SiteResourceAuthority
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from .worker_client import SupervisedSiteInstance
from . import step as step_runtime
from lab_generate_skill.adapters.slurm.worker_evidence import WorkerStepEvidence

diagnostic_candidates = WorkerStepEvidence("site").diagnostic_candidates
from .worker_protocol import SiteWorkerReply
from .resource_records import phase, fact, acknowledged


def close_site_resource(
    spec: SiteResourceSpec,
    client: SupervisedSiteInstance,
    attempt: SiteResourceAttempt,
    acquisition: OperationContext,
    intent_ref: EvidenceRef,
    *,
    journal: ResourceJournal,
    evidence: EvidenceStore,
    controls: OperationControls,
    clock: Clock,
    authority: SiteResourceAuthority,
    primary: BaseException | None,
    startup_reply: SiteWorkerReply | None,
    step: step_runtime.SiteStepState,
    cleanup_seconds: int = 30,
) -> None:
    errors: list[BaseException] = []
    record = None
    cleanup = None
    closure = None
    ending_ref = None
    step_closed = None
    process_stop = None
    observed_quiescence = None
    try:
        if type(cleanup_seconds) is not int or not 1 <= cleanup_seconds <= 3600:
            raise ValueError("Explicit bounded site metadata cleanup duration required")
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
            client.channel.abort(DeadlineControl(5, "site-emergency-abort"))
        except BaseException as emergency:
            errors.append(emergency)
    capture = client.channel.capture
    stop_control = DeadlineControl(15, "site-original-step-close")
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
                else DeadlineControl(5, "site-failed-clock-diagnostic")
            ),
        )
        if step_closed is not None and step_closed.target != attempt.target:
            raise OwnershipConflict("Site step closure changed original attempt target")
    except BaseException as error:
        if getattr(error, "site_step_physical_target", None) == attempt.target:
            observed_quiescence = getattr(error, "site_step_physical_quiescence", None)
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
        capture_ref = step_runtime.save(
            evidence,
            attempt.target,
            "worker-capture",
            [],
            [capture],
            (
                controls.bind(cleanup)
                if cleanup is not None
                else DeadlineControl(5, "site-worker-diagnostic")
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
                "Site complete-resource closure remains unconfirmed"
            )
        for ref in closure.evidence:
            if ref.visibility != "private":
                raise OwnershipConflict("Site closure facts must be private")
            evidence.read(ref, control=controls.bind(cleanup))
        if (
            capture.termination is None
            or capture.termination.state == "unconfirmed"
            or capture.termination.cleanup_errors
        ):
            raise OwnershipConflict("Site channel termination remains unconfirmed")
        if capture.termination.process_id != (
            None if attempt.launcher is None else attempt.launcher.process_id
        ):
            raise OwnershipConflict("Site termination changed original launcher")
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
                "worker_capture_ref": (
                    None if capture_ref is None else capture_ref.model_dump(mode="json")
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
    physical_observation = {
        "target": (
            None if attempt.target is None else attempt.target.model_dump(mode="json")
        ),
        "termination": (
            None if capture.termination is None else asdict(capture.termination)
        ),
        "process_stop": (
            None if process_stop is None else process_stop.model_dump(mode="json")
        ),
        "quiescence": (
            step_closed.quiescence.model_dump(mode="json")
            if step_closed is not None
            else (
                None
                if observed_quiescence is None
                else observed_quiescence.model_dump(mode="json")
            )
        ),
        "step_closure_evidence_returned": step_closed is not None,
        "durable_resource_close_confirmed": not errors,
        "safe_Reset_granted_by_this_observation": False,
    }
    if primary is not None:
        setattr(primary, "site_resource_physical_observation", physical_observation)
        setattr(primary, "command_capture", capture)
        setattr(primary, "site_resource_ending_ref", ending_ref)
        setattr(primary, "site_resource_attempt", attempt)
        setattr(primary, "site_resource_startup_reply", startup_reply)
    if errors:
        result = BaseExceptionGroup(
            "Site resource and cleanup failed",
            ([primary] if primary is not None else []) + errors,
        )
        setattr(result, "site_resource_physical_observation", physical_observation)
        setattr(result, "command_capture", capture)
        setattr(result, "site_resource_ending_ref", ending_ref)
        setattr(result, "site_resource_attempt", attempt)
        setattr(result, "site_resource_startup_reply", startup_reply)
        raise result from None
