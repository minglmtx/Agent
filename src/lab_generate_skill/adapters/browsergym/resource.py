"""Persistent once-only browser acquisition using the existing ResourceJournal.

Inputs fix an attempt token, complete worker configuration and mandatory live
resource authority. The returned published session is usable only inside with.
Register/begin acknowledgement precedes spawn; failed/unknown begin never grants
launch or cleanup of an earlier resource. Outer supervision still owns blocking
journal/authority I/O and original-controller failure containment.
"""

from contextlib import contextmanager
from collections.abc import Iterator
from lab_generate_skill.domain.browser_resource import (
    BrowserResourceSpec,
    BrowserResourceStarted,
    BrowserResourceAttempt,
    BrowserResourcePrepared,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import ResourceJournal, OperationControls, Clock
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.browser_resources import BrowserResourceAuthority
from lab_generate_skill.adapters.processes.session import FramedProcessSession
from .worker_client import SupervisedBrowserSession
from lab_generate_skill.adapters.slurm.step_launch import fixed_browser_step_argv
from . import step as step_runtime
from .worker_protocol import MAX_PACKET, BrowserWorkerReply
from .evidence_session import EvidenceBrowserSession
from .resource_authority import BoundBrowserAuthority
from .resource_records import phase, put, fact, acknowledged
from .resource_cleanup import close_browser_resource
from .acquisition import commit_original_worker
from .return_publication import BrowserReturnPublication


@contextmanager
def registered_browser(
    spec: BrowserResourceSpec,
    operation: OperationContext,
    *,
    journal: ResourceJournal,
    evidence: EvidenceStore,
    controls: OperationControls,
    clock: Clock,
    authority: BrowserResourceAuthority,
    cleanup_seconds: int = 30,
    return_publication: BrowserReturnPublication | None = None,
) -> Iterator[EvidenceBrowserSession]:
    if type(cleanup_seconds) is not int or not 1 <= cleanup_seconds <= 3600:
        raise ValueError("Explicit bounded browser metadata cleanup duration required")
    spec = BrowserResourceSpec.model_validate(spec)
    operation = OperationContext.model_validate(operation)
    spec.check_operation(operation, "execute")
    if return_publication is not None and return_publication.token != spec.token:
        raise EvidenceIntegrityError("Return publication changed browser allocation")
    control = controls.bind(operation)
    control.checkpoint()
    authority.authorize_start(spec, operation, control)
    channel = FramedProcessSession(
        fixed_browser_step_argv(
            spec.token,
            spec.slurm.execution,
            spec.slurm.parent.writer.node_id,
            python_executable=spec.configuration.installation.python_executable,
            srun_executable=spec.slurm.srun_executable,
        ),
        max_frame_bytes=MAX_PACKET,
    )
    step = step_runtime.BrowserStepState()
    prepared: BrowserResourcePrepared | None = None
    prepared_ref: EvidenceRef | None = None
    worker_acquired_ref: EvidenceRef | None = None

    def observe_configuration(
        reply: BrowserWorkerReply, op: OperationContext, bound: OperationControl
    ) -> None:
        nonlocal prepared, prepared_ref, worker_acquired_ref
        if op != operation or worker_acquired_ref is not None:
            raise EvidenceIntegrityError(
                "Original browser acquisition callback changed"
            )
        if reply.owner_guard is None or reply.installed_sources is None:
            raise EvidenceIntegrityError("Browser configuration lacks original facts")
        observed = step_runtime.observe_started(
            spec, step, reply.owner_guard, evidence, bound
        )
        prepared = BrowserResourcePrepared(
            step=observed,
            owner_guard=reply.owner_guard,
            installed_sources=reply.installed_sources,
        )
        prepared_ref = put(
            evidence,
            prepared.model_dump_json().encode(),
            prepared.schema_version,
            bound,
        )
        worker_acquired_ref = commit_original_worker(
            spec, prepared, prepared_ref, operation, acquiring, journal, evidence, bound
        )

    client = SupervisedBrowserSession(
        channel,
        spec.token.expected_resource_id,
        spec.configuration,
        BoundBrowserAuthority(spec, authority),
        configure_observer=observe_configuration,
    )
    step_runtime.check_parent(spec, client.controller, control)
    session = EvidenceBrowserSession(
        client, evidence, return_publication=return_publication, viewport_source=client
    )
    registered = journal.register(spec.token, phase(operation, "register"))
    if registered.token != spec.token:
        raise EvidenceIntegrityError("Browser registration changed token")
    config_ref = put(
        evidence, spec.model_dump_json().encode(), spec.schema_version, control
    )
    intent = ResourceAcquisitionIntent(
        token=spec.token, operation=operation, configuration_ref=config_ref
    )
    intent_ref = put(
        evidence,
        intent.model_dump_json().encode(),
        "resource-acquisition-intent/1",
        control,
    )
    acquiring = journal.begin_acquire(
        spec.token, intent_ref, registered.revision, operation
    )
    # No finally before first acknowledgement: an unknown begin owns no new
    # process and cannot close a different existing acquisition.
    primary: BaseException | None = None
    start_attempted = False
    started = None
    start_reply = None
    try:
        acquiring = acknowledged(
            acquiring, spec, "acquiring", operation, intent_ref, registered.revision + 1
        )
        control.checkpoint()
        start_attempted = True
        channel.start(control)
        if channel.process_id is None:
            raise EvidenceIntegrityError("Browser launcher identity was not returned")
        step.launcher = step_runtime.observe_launcher(spec, channel.process_id, control)
        initial = session.start(operation, control=control)
        start_reply = client.last_reply
        if (
            start_reply is None
            or prepared is None
            or prepared_ref is None
            or session.last_return_ref is None
            or worker_acquired_ref is None
        ):
            raise EvidenceIntegrityError("Browser start lacks original observed facts")
        started = BrowserResourceStarted(
            step=prepared.step,
            owner_guard=prepared.owner_guard,
            installed_sources=prepared.installed_sources,
            initial_observation_ref=initial,
            initial_return_ref=session.last_return_ref,
        )
        authority.verify_started(spec, started, operation, control)
        op = phase(operation, "acquired")
        ref = fact(
            evidence,
            spec,
            op,
            "acquired",
            {
                "started": started.model_dump(mode="json"),
                "worker_acquired_ref": worker_acquired_ref.model_dump(mode="json"),
            },
            control,
        )
        # Like site startup, initial readiness is a separate fact. The journal
        # already owns the original worker; never replace that acquisition.
        session.resource_started_ref = ref
        control.checkpoint()
        yield session
    except BaseException as error:
        primary = error
        setattr(error, "command_capture", channel.capture)
        raise
    finally:
        if (
            start_reply is None
            and client.last_reply is not None
            and client.last_reply.phase == "start"
        ):
            start_reply = client.last_reply
        # A mismatched candidate reply is diagnostic only, never an owned guard.
        owner_guard = prepared.owner_guard if prepared is not None else None
        attempt = BrowserResourceAttempt(
            start_attempted=start_attempted,
            launcher_pid=channel.process_id,
            launcher=step.launcher,
            target=step.target,
            owner_guard=owner_guard,
            prepared=prepared,
            prepared_ref=prepared_ref,
            started=started,
        )
        close_browser_resource(
            spec,
            client,
            attempt,
            operation,
            intent_ref,
            journal=journal,
            evidence=evidence,
            controls=controls,
            clock=clock,
            authority=authority,
            primary=primary,
            startup_reply=start_reply,
            initial_ready_ref=session.resource_started_ref,
            step=step,
            cleanup_seconds=cleanup_seconds,
        )
