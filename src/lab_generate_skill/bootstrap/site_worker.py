"""Fixed installed site child; original-parent guard precedes native effects."""

import os
import resource
import sys
import time
from typing import Literal
from lab_generate_skill.domain.release_installation import (
    ReleaseInstallation,
    InstalledReleaseSources,
)
from lab_generate_skill.adapters.processes.owner_supervisor import (
    supervise_owner,
    observed_guard,
)
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from lab_generate_skill.adapters.sites.worker_stream import read_command, serve
from lab_generate_skill.adapters.sites.worker_service import SiteService
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.site_worker import WorkerSiteInstance


def _progress(
    phase: Literal[
        "input_wait",
        "input_read",
        "guard_verified",
        "installation_begin",
        "installation_verified",
        "instance_factory",
    ],
) -> None:
    # Fixed phase labels only: no configuration, payload, path or credentials.
    sys.stderr.write(f"SITE_WORKER_PHASE {phase} {time.monotonic():.6f}\n")
    sys.stderr.flush()


def main() -> int:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    with os.fdopen(os.dup(sys.stdout.fileno()), "wb", buffering=0) as wire:
        os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
        try:
            _progress("input_wait")
            first = read_command(sys.stdin.buffer)
            _progress("input_read")
            if first is None:
                return 0
            if first.phase != "configure" or first.controller is None:
                raise ValueError("Site must configure with original controller")
            controller = first.controller

            def child(supervisor: ProcessIdentity, owner_fd: int) -> int:
                from lab_generate_skill.adapters.releases.installation import (
                    verify_release_installation,
                )
                from lab_generate_skill.bootstrap.site_instance import (
                    build_site_instance,
                )

                def verify(
                    expected: ProcessIdentity, control: OperationControl
                ) -> ProcessOwnerGuard:
                    if expected != controller:
                        raise ValueError("Original site controller changed")
                    result = observed_guard(controller, supervisor, owner_fd, control)
                    _progress("guard_verified")
                    return result

                def factory(
                    configuration: SiteWorkerConfiguration,
                ) -> WorkerSiteInstance:
                    _progress("instance_factory")

                    class OriginalGuard:
                        def observe(
                            self, control: OperationControl
                        ) -> ProcessOwnerGuard:
                            return verify(controller, control)

                    return build_site_instance(
                        configuration, worker_guard=OriginalGuard()
                    )

                def installation(
                    declaration: ReleaseInstallation, control: OperationControl
                ) -> InstalledReleaseSources:
                    _progress("installation_begin")
                    actual = verify_release_installation(declaration, control)
                    _progress("installation_verified")
                    return actual

                service = SiteService(factory, installation, verify)
                serve(service, sys.stdin.buffer, wire, first)
                return 0

            return supervise_owner(
                controller,
                DeadlineControl(first.remaining_seconds, "site-owner-pin"),
                child,
            )
        except BaseException as error:
            sys.stderr.write(
                "SITE_WORKER_FAILED " + describe_error(error).model_dump_json() + "\n"
            )
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
