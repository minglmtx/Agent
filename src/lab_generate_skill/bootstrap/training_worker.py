"""Fixed installed SFT supervisor; no dynamic entry point or inline fallback."""

import os
import resource
import sys
from lab_generate_skill.adapters.processes.stream_frames import read_frame
from lab_generate_skill.adapters.processes.framed_service import serve_framed
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from lab_generate_skill.adapters.processes.owner_supervisor import (
    supervise_owner,
    observed_guard,
)
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.training.worker_protocol import (
    MAX_PACKET,
    decode_command,
)
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.ports.lifecycle import OperationControl


def main() -> int:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.environ.update(
        HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TOKENIZERS_PARALLELISM="false"
    )
    with os.fdopen(os.dup(sys.stdout.fileno()), "wb", buffering=0) as wire:
        os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
        try:
            raw = read_frame(sys.stdin.buffer, MAX_PACKET)
            if raw is None:
                return 0
            first = decode_command(raw)
            if first.operation != "configure" or first.controller is None:
                raise ValueError(
                    "SFT worker requires original controller configuration first"
                )
            controller = first.controller

            def run_child(supervisor: ProcessIdentity, owner_fd: int) -> int:
                from lab_generate_skill.adapters.training.worker_service import (
                    TrainingWorkerService,
                )
                from lab_generate_skill.adapters.training.worker_backend import (
                    FixedTrainingBackend,
                )
                from lab_generate_skill.adapters.releases.installation import (
                    verify_release_installation,
                )

                def verify(
                    expected: ProcessIdentity, control: OperationControl
                ) -> ProcessOwnerGuard:
                    if expected != controller:
                        raise ValueError("Original SFT controller cannot change")
                    return observed_guard(controller, supervisor, owner_fd, control)

                service = TrainingWorkerService(
                    lambda configuration, guard: FixedTrainingBackend(
                        configuration, guard, owner_fd
                    ),
                    verify_release_installation,
                    verify,
                )
                serve_framed(
                    service,
                    sys.stdin.buffer,
                    wire,
                    decode=decode_command,
                    limit=MAX_PACKET,
                    first=first,
                )
                return 0

            return supervise_owner(
                controller,
                DeadlineControl(first.remaining_seconds, "sft-owner-pin"),
                run_child,
            )
        except BaseException as error:
            sys.stderr.write(
                "SFT_WORKER_PROTOCOL_OR_SUPERVISION_FAILED "
                + describe_error(error).model_dump_json()
                + "\n"
            )
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
