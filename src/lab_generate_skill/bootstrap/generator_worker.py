"""Fixed installed parent supervisor; model service runs only in its guarded child."""

import os
import resource
import sys
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from lab_generate_skill.adapters.models.generator_worker_stream import (
    read_command,
    serve,
)
from lab_generate_skill.adapters.processes.owner_supervisor import (
    supervise_owner,
    observed_guard,
)
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.ports.lifecycle import OperationControl


def main() -> int:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    with os.fdopen(os.dup(sys.stdout.fileno()), "wb", buffering=0) as wire:
        os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
        try:
            first = read_command(sys.stdin.buffer)
            if first is None:
                return 0
            if (
                first.operation != "configure"
                or first.sequence != 1
                or first.controller is None
            ):
                raise ValueError(
                    "First worker command must configure its original controller"
                )
            controller = first.controller

            def run_child(supervisor: ProcessIdentity, owner_fd: int) -> int:
                # No engine factory or model library before kernel supervision.
                from lab_generate_skill.adapters.models.generator_service import (
                    GeneratorService,
                )
                from lab_generate_skill.adapters.models.generator_installation import (
                    verify_generator_installation,
                )
                from lab_generate_skill.adapters.models.transformers_generator import (
                    ResidentGeneratorEngine,
                )

                def verify(
                    expected: ProcessIdentity, control: OperationControl
                ) -> ProcessOwnerGuard:
                    if expected != controller:
                        raise ValueError("Original controller cannot change")
                    return observed_guard(controller, supervisor, owner_fd, control)

                service = GeneratorService(
                    ResidentGeneratorEngine, verify_generator_installation, verify
                )
                serve(service, sys.stdin.buffer, wire, first=first)
                return 0

            return supervise_owner(
                controller,
                DeadlineControl(first.remaining_seconds, "owner-pin"),
                run_child,
            )
        except BaseException as error:
            sys.stderr.write(
                "GENERATOR_WORKER_PROTOCOL_OR_SUPERVISION_FAILED "
                + describe_error(error).model_dump_json()
                + "\n"
            )
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
