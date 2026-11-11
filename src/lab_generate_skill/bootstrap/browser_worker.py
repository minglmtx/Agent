"""Fixed installed BrowserGym entry, guarded before installation/native effects.

Business permission and durable launch intent belong to the original parent.
This child never loads a dynamic plugin/factory supplied by a command. It checks
actual original-parent supervision and exact installed code, then one session.
"""

import os
import resource
import sys
from lab_generate_skill.adapters.processes.owner_supervisor import (
    supervise_owner,
    observed_guard,
)
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from lab_generate_skill.adapters.browsergym.worker_stream import read_command, serve
from lab_generate_skill.adapters.browsergym.worker_service import BrowserService
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.adapters.browsergym.worker_protocol import Phase
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.browser_session import RawBrowserSession


def main() -> int:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    with os.fdopen(os.dup(sys.stdout.fileno()), "wb", buffering=0) as wire:
        os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
        try:
            first = read_command(sys.stdin.buffer)
            if first is None:
                return 0
            if first.phase != "configure" or first.controller is None:
                raise ValueError("Browser must start with its original controller")
            controller = first.controller

            def child(supervisor: ProcessIdentity, owner_fd: int) -> int:
                from lab_generate_skill.adapters.clock import SystemClock
                from lab_generate_skill.bootstrap.browser_engine import (
                    build_browser_engine,
                )
                from lab_generate_skill.adapters.browsergym.storage_guard import (
                    OriginalBrowserProcessGuard,
                )
                from lab_generate_skill.adapters.releases.installation import (
                    verify_release_installation,
                )

                def verify(
                    expected: ProcessIdentity, control: OperationControl
                ) -> ProcessOwnerGuard:
                    if expected != controller:
                        raise ValueError("Original browser controller changed")
                    return observed_guard(controller, supervisor, owner_fd, control)

                class OriginalParentDelegation:
                    def verify(
                        self,
                        spec: BrowserSessionSpec,
                        phase: Phase,
                        action: BrowserAction | None,
                        operation: OperationContext,
                        control: OperationControl,
                    ) -> None:
                        verify(controller, control)

                def factory(
                    configuration: BrowserWorkerConfiguration,
                ) -> RawBrowserSession:
                    return build_browser_engine(
                        configuration,
                        OriginalParentDelegation(),
                        SystemClock(),
                        worker_guard=OriginalBrowserProcessGuard(
                            controller, supervisor, owner_fd
                        ),
                    )

                service = BrowserService(factory, verify_release_installation, verify)
                serve(service, sys.stdin.buffer, wire, first)
                return 0

            return supervise_owner(
                controller,
                DeadlineControl(first.remaining_seconds, "browser-owner-pin"),
                child,
            )
        except BaseException as error:
            sys.stderr.write(
                "BROWSER_WORKER_FAILED "
                + describe_error(error).model_dump_json()
                + "\n"
            )
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
