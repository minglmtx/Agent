"""One original registered site, with ownership durable before native startup.

No default authority, implicit retry, replacement resource or local I/O fallback.
Journal/authority/evidence I/O must run under the existing outer supervision.
Acquired denotes worker ownership; only a verified SiteResourceStarted is yielded.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from lab_generate_skill.ports.site_tasks import SiteTasks
from lab_generate_skill.ports.site_resume import ParentSiteResume
from collections.abc import Callable, Iterator
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceAttempt,
    SiteResourceStarted,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import ResourceJournal, OperationControls, Clock
from lab_generate_skill.ports.site_resources import SiteResourceAuthority
from lab_generate_skill.adapters.processes.session import FramedProcessSession
from lab_generate_skill.adapters.slurm.step_launch import fixed_site_step_argv
from lab_generate_skill.ports.site_capture import ParentSiteCapture
from .worker_client import SupervisedSiteInstance
from .worker_protocol import MAX_PACKET
from .resource_authority import BoundSiteAuthority
from .resource_records import phase, put, fact, acknowledged
from .resource_cleanup import close_site_resource
from . import step as step_runtime


@dataclass(frozen=True)
class RegisteredSite:
    site: SiteResourceStarted
    tasks: SiteTasks
    resume: ParentSiteResume
    capture: ParentSiteCapture


@contextmanager
def registered_site(
    spec: SiteResourceSpec,
    operation: OperationContext,
    *,
    journal: ResourceJournal,
    evidence: EvidenceStore,
    controls: OperationControls,
    clock: Clock,
    authority: SiteResourceAuthority,
    cleanup_seconds: int = 30,
    registration_boundary: Callable[[], None] | None = None,
) -> Iterator[RegisteredSite]:
    if type(cleanup_seconds) is not int or not 1 <= cleanup_seconds <= 3600:
        raise ValueError("Explicit bounded site metadata cleanup duration required")
    if registration_boundary is not None and not callable(registration_boundary):
        raise TypeError("Site registration boundary must be callable or None")
    spec = SiteResourceSpec.model_validate(spec)
    operation = OperationContext.model_validate(operation)
    spec.check_operation(operation, "execute")
    control = controls.bind(operation)
    control.checkpoint()
    authority.authorize_spawn(spec, operation, control)
    channel = FramedProcessSession(
        fixed_site_step_argv(
            spec.token,
            spec.slurm.execution,
            spec.slurm.parent.writer.node_id,
            python_executable=spec.configuration.installation.python_executable,
            srun_executable=spec.slurm.srun_executable,
        ),
        max_frame_bytes=MAX_PACKET,
    )
    bound = BoundSiteAuthority(spec, operation, authority)
    client = SupervisedSiteInstance(
        channel, spec.token.expected_resource_id, spec.configuration, bound
    )
    step = step_runtime.SiteStepState()
    step_runtime.check_parent(spec, client.controller, control)
    if registration_boundary is not None:
        registration_boundary()
    registered = journal.register(spec.token, phase(operation, "register"))
    if registered.token != spec.token:
        raise EvidenceIntegrityError("Site registration changed original token")
    config_ref = put(
        evidence, spec.model_dump_json().encode(), spec.schema_version, control
    )
    intent = ResourceAcquisitionIntent(
        token=spec.token, operation=operation, configuration_ref=config_ref
    )
    intent_ref = put(
        evidence, intent.model_dump_json().encode(), intent.schema_version, control
    )
    acquiring = journal.begin_acquire(
        spec.token, intent_ref, registered.revision, operation
    )
    # An unacknowledged begin never grants a new launch or cleanup of an old one.
    primary: BaseException | None = None
    spawn_attempted = start_attempted = False
    started = None
    try:
        acquiring = acknowledged(
            acquiring, spec, "acquiring", operation, intent_ref, registered.revision + 1
        )
        control.checkpoint()
        spawn_attempted = True
        channel.start(control)
        if channel.process_id is None:
            raise EvidenceIntegrityError("Site launcher identity was not returned")
        step.launcher = step_runtime.observe_launcher(spec, channel.process_id, control)
        prepared = client.configure(operation, control=control)
        ready = step_runtime.observe_ready(spec, step, prepared, evidence, control)
        authority.verify_ready(spec, ready, operation, control)
        op = phase(operation, "acquired")
        ref = fact(
            evidence,
            spec,
            op,
            "acquired",
            {"ready": ready.model_dump(mode="json"), "site_started": False},
            control,
        )
        acknowledged(
            journal.advance(spec.token, "acquired", (ref,), acquiring.revision, op),
            spec,
            "acquired",
            op,
            ref,
            acquiring.revision + 1,
        )
        bound.acquired_ref = ref
        control.checkpoint()
        start_attempted = True
        started = client.start(operation, control=control)
        authority.verify_started(spec, ready, started, operation, control)
        start_ref = fact(
            evidence,
            spec,
            phase(operation, "site-started"),
            "acquired",
            {
                "ready_ref": ref.model_dump(mode="json"),
                "started": started.model_dump(mode="json"),
            },
            control,
        )
        result = SiteResourceStarted(ready=ready, instance=started, evidence=start_ref)
        control.checkpoint()
        yield RegisteredSite(result, client, client, client)
    except BaseException as error:
        primary = error
        setattr(error, "command_capture", channel.capture)
        raise
    finally:
        attempt = SiteResourceAttempt(
            spawn_attempted=spawn_attempted,
            launcher=step.launcher,
            target=step.target,
            ready=step.ready,
            start_attempted=start_attempted,
            started=started,
        )
        close_site_resource(
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
            startup_reply=client.last_reply,
            step=step,
            cleanup_seconds=cleanup_seconds,
        )
