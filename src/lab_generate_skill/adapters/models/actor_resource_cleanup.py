"""Independent cleanup of the one acknowledged Actor acquisition.

Persistence failure must not skip physical close. A close or authority failure
cannot become a clean receipt. Always preserve the original body/start error and
all bookkeeping/physical/verification errors; never launch a replacement.
"""

from dataclasses import asdict
from lab_generate_skill.domain.actor_resource import ActorResourceSpec
from lab_generate_skill.domain.lifecycle import OperationContext, ResourceState
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import ResourceJournal, OperationControls
from lab_generate_skill.ports.actor_resources import ActorResourceAuthority
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from .actor_worker_client import SupervisedActorEngine
from .actor_step import ActorStepState
from lab_generate_skill.domain.actor_step import (
    ActorStepCleanup,
    ActorStepClosed,
)
from .actor_resource_records import phase, fact, acknowledged, check_operation


def close_actor_resource(
    spec: ActorResourceSpec,
    engine: SupervisedActorEngine,
    step: ActorStepState,
    op: OperationContext,
    journal: ResourceJournal,
    evidence: EvidenceStore,
    controls: OperationControls,
    authority: ActorResourceAuthority,
    primary: BaseException | None,
) -> None:
    check_operation(spec, op, "cleanup")
    errors: list[BaseException] = []
    record = None
    try:
        record = journal.read(spec.token, phase(op, "inspect"))
        if record.token != spec.token or record.state not in (
            "acquiring",
            "acquired",
            "closing",
        ):
            raise OwnershipConflict("Cleanup must retain original active acquisition")
        if record.state != "closing":
            closing_op = phase(op, "closing")
            ref = fact(
                evidence, spec, closing_op, "closing", {}, control=controls.bind(op)
            )
            record = acknowledged(
                journal.advance(
                    spec.token, "closing", (ref,), record.revision, closing_op
                ),
                spec,
                "closing",
                closing_op,
                ref,
                record.revision + 1,
            )
    except BaseException as error:
        errors.append(error)
    # Independent local physical guard: ledger/authority I/O may already have
    # consumed the bookkeeping deadline. Always stop this original handle.
    try:
        engine.close(DeadlineControl(10, "actor-physical-close"))
    except BaseException as error:
        errors.append(error)
    capture = engine.capture
    termination = capture.termination
    clean = False
    closure = None
    try:
        if (
            termination is None
            or termination.state == "unconfirmed"
            or termination.cleanup_errors
        ):
            raise OwnershipConflict("Actor termination is unconfirmed")
        owned = ActorStepCleanup(
            start_attempted=step.start_attempted,
            launcher=step.launcher,
            target=step.target,
            started=step.started,
        )
        returned = authority.verify_closed(
            spec, owned, termination, op, controls.bind(op)
        )
        if returned is None:
            if step.start_attempted or termination.state != "not_started":
                raise OwnershipConflict(
                    "Attempted resource cannot omit original closure proof"
                )
        else:
            verified = ActorStepClosed.model_validate(returned)
            if verified.target != step.target:
                raise OwnershipConflict(
                    "Authority closure belongs to another original step"
                )
            evidence.read(verified.evidence, control=controls.bind(op))
            closure = verified
        controls.bind(op).checkpoint()
        clean = not errors
    except BaseException as error:
        errors.append(error)
    ending_ref = None
    try:
        ending_op = phase(op, "ended")
        state: ResourceState = "closed" if clean else "quarantined"
        ending_ref = fact(
            evidence,
            spec,
            ending_op,
            state,
            {
                "start_attempted": step.start_attempted,
                "launcher": (
                    None
                    if step.launcher is None
                    else step.launcher.model_dump(mode="json")
                ),
                "target": (
                    None if step.target is None else step.target.model_dump(mode="json")
                ),
                "step_started": (
                    None
                    if step.started is None
                    else step.started.model_dump(mode="json")
                ),
                "step_closed": (
                    None if closure is None else closure.model_dump(mode="json")
                ),
                "termination": None if termination is None else asdict(termination),
                "primary": (
                    None
                    if primary is None
                    else describe_error(primary).model_dump(mode="json")
                ),
                "primary_step_evidence": (
                    getattr(primary, "actor_step_evidence_ref").model_dump(mode="json")
                    if primary is not None
                    and hasattr(primary, "actor_step_evidence_ref")
                    else None
                ),
                "cleanup_step_evidence": [
                    (
                        getattr(e, "actor_step_evidence_ref").model_dump(mode="json")
                        if hasattr(e, "actor_step_evidence_ref")
                        else None
                    )
                    for e in errors
                ],
                "cleanup_errors": [
                    describe_error(e).model_dump(mode="json") for e in errors
                ],
            },
            control=controls.bind(op),
        )
        if record is None or record.state != "closing":
            raise OwnershipConflict(
                "Closing not acknowledged; retain ended fact for reconciliation"
            )
        acknowledged(
            journal.advance(
                spec.token, state, (ending_ref,), record.revision, ending_op
            ),
            spec,
            state,
            ending_op,
            ending_ref,
            record.revision + 1,
        )
    except BaseException as error:
        if ending_ref is not None:
            setattr(error, "actor_resource_ending_ref", ending_ref)
        errors.append(error)
    if primary is not None:
        setattr(primary, "command_capture", capture)
    if errors:
        combined = BaseExceptionGroup(
            "Actor resource and cleanup failed",
            ([primary] if primary is not None else []) + errors,
        )
        setattr(combined, "command_capture", capture)
        raise combined from None
