"""One registered fixed Actor process, scoped to the caller's with block.

Acquisition is persistent and single-use across new Python objects/processes.
This adapter composes existing journal/session/engine implementations. It never
chooses a release, authorizes itself, retries a launch or recreates old resources.
The enclosing Slurm/supervisor must also bound ledger/authority I/O and parent
failure; cooperative checkpoints alone do not provide that outer containment.
"""

import hashlib
from pathlib import Path
from contextlib import contextmanager
from collections.abc import Iterator
from lab_generate_skill.domain.actor_resource import ActorResourceSpec
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import ResourceJournal, OperationControls, Clock
from lab_generate_skill.ports.actor_resources import ActorResourceAuthority
from lab_generate_skill.adapters.processes.session import FramedProcessSession
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from .actor_worker_protocol import MAX_WORKER_PACKET
from .actor_worker_client import SupervisedActorEngine
from .actor_resource_records import phase, put, fact, acknowledged, check_operation
from .actor_resource_cleanup import close_actor_resource
from .actor_release import verify_actor_release
from .actor_step import (
    ActorStepState,
    same_allocation,
    observe_launcher,
    observe_started,
    retain_step_failure,
)
from lab_generate_skill.adapters.slurm.allocation import SlurmAllocationVerifier
from lab_generate_skill.adapters.slurm.step_launch import fixed_actor_step_argv


@contextmanager
def registered_actor(
    spec: ActorResourceSpec,
    op: OperationContext,
    *,
    journal: ResourceJournal,
    evidence: EvidenceStore,
    controls: OperationControls,
    clock: Clock,
    authority: ActorResourceAuthority,
    workspace_root: Path,
    allocation_verifier: SlurmAllocationVerifier,
    cleanup_seconds: int = 30,
) -> Iterator[SupervisedActorEngine]:
    if type(cleanup_seconds) is not int or not 1 <= cleanup_seconds <= 3600:
        raise ValueError("Explicit bounded Actor metadata cleanup duration required")
    spec, op = ActorResourceSpec.model_validate(spec), OperationContext.model_validate(
        op
    )
    check_operation(spec, op, "execute")
    control = controls.bind(op)
    control.checkpoint()
    released = verify_actor_release(spec, evidence, workspace_root, control)
    original = spec.slurm.allocation
    allocation = allocation_verifier.observe(
        original.facts.execution, original.facts.writer, phase(op, "allocation-check")
    )
    same_allocation(original, allocation)
    authority.authorize_start(spec, op, control)
    control.checkpoint()
    # Construct/validate all owned handles before committing acquisition intent.
    channel = FramedProcessSession(
        fixed_actor_step_argv(
            spec.token,
            allocation.facts.execution,
            allocation.facts.writer.node_id,
            python_executable=spec.python_executable,
            srun_executable=spec.slurm.srun_executable,
        ),
        max_frame_bytes=MAX_WORKER_PACKET,
        cuda_visible_devices=allocation.facts.gpu.uuid,
    )
    step = ActorStepState()
    engine = SupervisedActorEngine(
        channel,
        spec.token.expected_resource_id,
        spec.artifact,
        spec.engine_config,
        ReleaseInstallation(
            manifest_ref=spec.release_ref,
            manifest=released.manifest,
            workspace_root=str(workspace_root),
            python_executable=spec.python_executable,
        ),
    )
    registered = journal.register(spec.token, phase(op, "register"))
    if registered.token != spec.token:
        raise EvidenceIntegrityError("Registration belongs to another allocation")
    configuration = put(
        evidence,
        spec.model_dump_json().encode(),
        "actor-resource-spec/1",
        control=control,
    )
    intent = ResourceAcquisitionIntent(
        token=spec.token, operation=op, configuration_ref=configuration
    )
    intent_ref = put(
        evidence,
        intent.model_dump_json().encode(),
        "resource-acquisition-intent/1",
        control=control,
    )
    acquired = journal.begin_acquire(spec.token, intent_ref, registered.revision, op)
    # A failed/unknown begin grants no resource ownership and must not clean a
    # possibly different live process from an earlier acknowledged acquisition.
    primary: BaseException | None = None
    acquisition_complete = False
    try:
        acquired = acknowledged(
            acquired, spec, "acquiring", op, intent_ref, registered.revision + 1
        )
        control.checkpoint()
        step.start_attempted = True
        channel.start(control)
        if channel.process_id is None:
            raise EvidenceIntegrityError("Step launcher identity was not returned")
        step.launcher = observe_launcher(
            channel.process_id, allocation.facts.execution.uid, control
        )
        worker = engine.configure(control)
        started = observe_started(spec, allocation, step, worker, evidence, control)
        authority.verify_started(spec, started, op, control)
        control.checkpoint()
        started_op = phase(op, "acquired")
        assert engine.installed_sources is not None and engine.owner_guard is not None
        ref = fact(
            evidence,
            spec,
            started_op,
            "acquired",
            {
                "worker": worker.model_dump(mode="json"),
                "owner_guard": engine.owner_guard.model_dump(mode="json"),
                "step": started.model_dump(mode="json"),
                "installed_sources": engine.installed_sources.model_dump(mode="json"),
            },
            control=control,
        )
        acknowledged(
            journal.advance(
                spec.token, "acquired", (ref,), acquired.revision, started_op
            ),
            spec,
            "acquired",
            started_op,
            ref,
            acquired.revision + 1,
        )
        control.checkpoint()
        acquisition_complete = True
        yield engine
    except BaseException as error:
        primary = error
        setattr(error, "command_capture", engine.capture)
        if not acquisition_complete:
            try:
                retain_step_failure(evidence, step, "acquisition", [], [], error)
            except BaseException as acquisition_failure:
                primary = acquisition_failure
                setattr(acquisition_failure, "command_capture", engine.capture)
                raise
        # A yielded task failure is recorded with its original capture by the
        # bounded resource finalizer. It is not a failed model acquisition and
        # must not quarantine storage through a short startup-diagnostic write.
        raise
    finally:
        try:
            cleanup = op.cleanup(
                "actor-cleanup-" + hashlib.sha256(op.operation_id.encode()).hexdigest(),
                now=clock.utcnow(),
                seconds=cleanup_seconds,
            )
        except BaseException as clock_error:
            failures = ([primary] if primary is not None else []) + [clock_error]
            try:
                engine.close(DeadlineControl(10, "actor-clock-failure-close"))
            except BaseException as close_error:
                failures.append(close_error)
            combined = BaseExceptionGroup(
                "Actor cleanup context and resource failed", failures
            )
            setattr(combined, "command_capture", engine.capture)
            raise combined from None
        close_actor_resource(
            spec,
            engine,
            step,
            cleanup,
            journal,
            evidence,
            controls,
            authority,
            primary,
        )
