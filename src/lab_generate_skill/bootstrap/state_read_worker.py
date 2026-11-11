"""Fixed installed pure state graph reader under the original parent's deadline."""

import hashlib
from pathlib import Path
import resource
import sys
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.plans.state_read_protocol import (
    MAX_PACKET,
    StateReadReply,
    decode_command,
    encode_reply,
)
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.processes.remote_errors import (
    describe_error,
    RemoteError,
)
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.storage.readonly_state_proof import (
    original_state_proof,
)
from lab_generate_skill.adapters.storage.readonly_evidence import ReadOnlyEvidence
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import CancellationRef
from lab_generate_skill.domain.state_qualification import (
    EnvironmentSelection,
    ResetSelection,
    QualifiedResetChecks,
)
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.release_installation import InstalledReleaseSources
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.runtime.lifecycle import OperationGuards
from .state_read_bindings import bind_state_read_checks


def serve(raw: bytes, controls: OperationControls) -> bytes:
    command = decode_command(raw)
    control = controls.bind(command.scope.operation)
    worker = current_process_identity()
    installed: InstalledReleaseSources | None = None
    environment: EnvironmentBaseline | None = None
    reset: QualifiedResetChecks | None = None
    error: RemoteError | None = None
    evidence: ReadOnlyEvidence | None = None
    try:
        with original_state_proof(
            command.scope, Path(command.workspace_root), controls, control
        ) as (evidence, installed):
            checks = bind_state_read_checks(command.task, evidence)
            selection = command.selection
            reads = StateReads(evidence)
            if isinstance(selection, EnvironmentSelection):
                actual = reads.parse(
                    command.selection_ref,
                    selection.schema_version,
                    EnvironmentSelection,
                    control,
                )
                if actual != selection:
                    raise OwnershipConflict(
                        "State proof changed original environment selection"
                    )
                assert command.operation is not None
                environment = checks.environment(
                    actual, command.selection_ref, command.operation, control
                )
            else:
                restored = reads.parse(
                    command.selection_ref,
                    selection.schema_version,
                    ResetSelection,
                    control,
                )
                if restored != selection:
                    raise OwnershipConflict(
                        "State proof changed original Reset selection"
                    )
                reset = checks.reset(restored, command.selection_ref, control)
                if reset.plan.scope.task != command.task:
                    raise OwnershipConflict("State proof changed original Reset task")
    except BaseException as caught:
        environment = reset = None
        error = describe_error(caught)
    return encode_reply(
        StateReadReply(
            request_sha256=hashlib.sha256(raw).hexdigest(),
            worker=worker,
            installed_sources=installed,
            environment=environment,
            reset=reset,
            error=error,
            read_count=0 if evidence is None else evidence.read_count,
            body_read_count=0 if evidence is None else evidence.body_read_count,
            unique_objects=0 if evidence is None else len(evidence.unique_objects),
        )
    )


class ParentCancellation:
    def is_cancelled(self, reference: CancellationRef) -> bool:
        raise ValueError("State proof delegates cancellation to its original parent")


def main() -> int:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        raw = sys.stdin.buffer.read(MAX_PACKET + 1)
        reply = serve(raw, OperationGuards(SystemClock(), ParentCancellation()))
        sys.stdout.buffer.write(reply)
        sys.stdout.buffer.flush()
    except BaseException:
        sys.stderr.write("STATE_READ_PROTOCOL_OR_OUTPUT_FAILED\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
