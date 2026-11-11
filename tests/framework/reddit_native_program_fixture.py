"""Read-only original image + tiny owned controls; no data copy or DB daemon."""

from pathlib import Path
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.native_commands import CheckedNativeCommands
from lab_generate_skill.sites.reddit.service_contract import (
    RedditServiceSpec,
    RedditPorts,
    IMAGE_SHA256,
    IMAGE_BYTES,
)

WORKSPACE = Path("/anvme/workspace/r102bf10-lab-generate-skill")
IMAGE = WORKSPACE / "assets/webarena/reddit" / IMAGE_SHA256 / "reddit.sif"
ENV = 'DATABASE_URL="old-private-db"\nUPLOAD_DSN="old-private-store"\nUPLOAD_ROOT="/old"\nAPP_SECRET="engineering-only-not-a-real-secret"\n'


def prepare(root: Path) -> RedditServiceSpec:
    for name in ["state", "control", "runtime"]:
        (root / name).mkdir(mode=0o700)
    for name in ["nginx", "uploads", "session", "media-native"]:
        (root / "state" / name).mkdir(mode=0o700)
    (root / "state/app.env").write_text(ENV)
    (root / "state/app.env").chmod(0o600)
    return RedditServiceSpec(
        files=SiteFilesPlan(
            instance_id="reddit-config-only",
            workspace_root=str(WORKSPACE),
            source_path=str(IMAGE),
            node_root=str(root),
            image=ReleaseFile(
                path="reddit.sif",
                sha256=IMAGE_SHA256,
                size_bytes=IMAGE_BYTES,
                executable=False,
            ),
        ),
        ports=RedditPorts(web=12001, database=12002),
    )


class OriginalImageCommands:
    """Explicit control-only adapter substitutes readonly source for copied SIF."""

    def __init__(self, spec: RedditServiceSpec) -> None:
        self.spec = spec
        self.commands = CheckedNativeCommands(
            ProcessRunner(max_output_bytes=256 * 1024)
        )
        self.calls: list[tuple[str, ...]] = []

    def command(self, argv: tuple[str, ...]) -> tuple[str, ...]:
        if argv.count(
            self.spec.files.image_path
        ) != 1 or self.spec.files.source_path != str(IMAGE):
            raise ValueError(
                "Only exact original read-only image fixture command accepted"
            )
        index = argv.index(self.spec.files.image_path)
        return (*argv[:index], str(IMAGE), *argv[index + 1 :])

    def run(self, argv: tuple[str, ...], control: OperationControl) -> bytes:
        self.calls.append(argv)
        return self.commands.run(self.command(argv), control)
