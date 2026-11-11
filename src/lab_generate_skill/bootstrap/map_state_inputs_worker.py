"""Read the fixed Map CAS input graph under original namespace supervision.

Native files, state semantics and actual site rights remain at the parent.
The check action revalidates the same namespace after that parent proof.
"""

import hashlib
from pathlib import Path
import resource
import sys
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.map_artifacts.state_input_graph import (
    MapStateInputCollector,
)
from lab_generate_skill.adapters.map_artifacts.state_input_protocol import (
    MAX_PACKET,
    MapStateInputsReply,
    decode_command,
    encode_reply,
)
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.storage.readonly_state_proof import (
    original_state_proof,
)
from lab_generate_skill.domain.lifecycle import CancellationRef
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.runtime.lifecycle import OperationGuards


def serve(raw: bytes, controls: OperationControls) -> bytes:
    command = decode_command(raw)
    control = controls.bind(command.scope.operation)
    installed = None
    bodies = None
    evidence = None
    error = None
    try:
        with original_state_proof(
            command.scope, Path(command.workspace_root), controls, control
        ) as (evidence, installed):
            if command.action == "inputs":
                bodies = MapStateInputCollector(evidence, control).collect(
                    command.selection, command.selection_ref, command.task
                )
    except BaseException as caught:
        bodies = None
        error = describe_error(caught)
    return encode_reply(
        MapStateInputsReply(
            request_sha256=hashlib.sha256(raw).hexdigest(),
            action=command.action,
            worker=current_process_identity(),
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
        raise ValueError("Map input cancellation is controlled by its original parent")


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
        sys.stderr.write("MAP_STATE_INPUT_PROTOCOL_OR_OUTPUT_FAILED\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
