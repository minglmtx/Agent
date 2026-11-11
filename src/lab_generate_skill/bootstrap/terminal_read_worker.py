"""Fixed installed terminal reader using the existing original state proof scope."""

import hashlib
from pathlib import Path
import resource
import sys
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.plans.terminal_read_protocol import (
    MAX_PACKET,
    TerminalReadReply,
    decode_command,
    encode_reply,
)
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
from lab_generate_skill.domain.lifecycle import CancellationRef
from lab_generate_skill.domain.release_installation import InstalledReleaseSources
from lab_generate_skill.domain.terminal_read import TerminalReadBodies
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.runtime.lifecycle import OperationGuards
from .terminal_read_bindings import read_terminal_bodies


def serve(raw: bytes, controls: OperationControls) -> bytes:
    command = decode_command(raw)
    control = controls.bind(command.scope.operation)
    worker = current_process_identity()
    installed: InstalledReleaseSources | None = None
    bodies: TerminalReadBodies | None = None
    error: RemoteError | None = None
    evidence: ReadOnlyEvidence | None = None
    try:
        with original_state_proof(
            command.scope, Path(command.workspace_root), controls, control
        ) as (evidence, installed):
            bodies = read_terminal_bodies(
                command.request, evidence, control, purpose=command.purpose
            )
    except BaseException as caught:
        bodies = None
        error = describe_error(caught)
    return encode_reply(
        TerminalReadReply(
            request_sha256=hashlib.sha256(raw).hexdigest(),
            worker=worker,
            installed_sources=installed,
            bodies=bodies,
            error=error,
            read_count=0 if evidence is None else evidence.read_count,
            body_read_count=0 if evidence is None else evidence.body_read_count,
            unique_objects=0 if evidence is None else len(evidence.unique_objects),
        )
    )


class ParentCancellation:
    def is_cancelled(self, reference: CancellationRef) -> bool:
        raise ValueError("Terminal proof delegates cancellation to its original parent")


def main() -> int:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        reply = serve(
            sys.stdin.buffer.read(MAX_PACKET + 1),
            OperationGuards(SystemClock(), ParentCancellation()),
        )
        sys.stdout.buffer.write(reply)
        sys.stdout.buffer.flush()
    except BaseException:
        sys.stderr.write("TERMINAL_READ_PROTOCOL_OR_OUTPUT_FAILED\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
