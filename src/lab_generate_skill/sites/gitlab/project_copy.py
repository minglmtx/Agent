"""Original selected-project COPY bytes through the existing native command port."""

import math
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.domain.evidence_io import MAX_OBJECT_BYTES
from lab_generate_skill.ports.lifecycle import Clock, OperationControl
from lab_generate_skill.ports.native_input_commands import NativeInputCommands
from .service_contract import GitlabServiceSpec
from .service_commands import container
from .tasks.group_spec import GroupSpec

PROJECT_COPY = "COPY (SELECT id,namespace_id,name,path FROM projects ORDER BY id) TO STDOUT WITH CSV"
PROJECT_ARGV = (
    "/opt/gitlab/embedded/bin/psql",
    "-h",
    "/var/opt/gitlab/postgresql",
    "-U",
    "gitlab",
    "-d",
    "gitlabhq_production",
    "-c",
    PROJECT_COPY,
)


class ProjectCopyControl:
    """Freeze the original180s process bound once, intersect every caller check."""

    def __init__(self, caller: OperationControl, clock: Clock) -> None:
        self.caller, self.clock = caller, clock
        self.ceiling = min(180.0, caller.checkpoint())
        self.deadline = clock.monotonic() + self.ceiling
        self.checkpoint()

    def checkpoint(self) -> float:
        self.ceiling = min(
            self.ceiling,
            self.deadline - self.clock.monotonic(),
            self.caller.checkpoint(),
        )
        if not math.isfinite(self.ceiling) or self.ceiling <= 0:
            raise OperationStopped("DEADLINE_EXCEEDED", "gitlab-project-copy")
        return self.ceiling

    def wait(self, seconds: float) -> None:
        if (
            type(seconds) not in (int, float)
            or not math.isfinite(seconds)
            or seconds < 0
        ):
            raise ValueError("Finite nonnegative native COPY wait required")
        self.caller.wait(min(seconds, self.checkpoint()))
        self.checkpoint()


class GitlabProjectCopyReader:
    def __init__(
        self, services: GitlabServiceSpec, commands: NativeInputCommands, clock: Clock
    ) -> None:
        self.services = GitlabServiceSpec.model_validate(services)
        self.commands, self.clock = commands, clock
        self.captured_raw: bytes | None = None

    def capture(self, spec: GroupSpec, control: OperationControl) -> bytes:
        self.captured_raw = None
        GroupSpec.model_validate(spec)
        bounded = ProjectCopyControl(control, self.clock)
        # psql executes only the exact original -c COPY. The newline satisfies
        # the existing nonempty stdin contract; it supplies no SQL or values.
        raw = self.commands.run_input(
            container(self.services) + PROJECT_ARGV, b"\n", bounded
        )
        if type(raw) is not bytes or len(raw) > MAX_OBJECT_BYTES:
            raise ValueError(
                "Complete original project COPY exceeds private byte bound"
            )
        self.captured_raw = raw  # empty COPY is a complete zero-row result
        bounded.checkpoint()
        return raw
