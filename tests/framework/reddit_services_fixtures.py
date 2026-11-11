"""Explicit native port fakes; no Postmill server/database or permission."""

from pathlib import Path
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.reddit.service_contract import (
    RedditServiceSpec,
    RedditPorts,
    IMAGE_SHA256,
    IMAGE_BYTES,
)
from lab_generate_skill.sites.reddit.service_programs import (
    SEED,
    CONFIGURE,
    POSTGRES_READY,
    TRUST_ACCOUNT,
    HTTP_READY,
)

from lab_generate_skill.sites.reddit.media_initialization_program import (
    INITIALIZE_MEDIA,
)

# Generic NativeServices identity/exit fake only; no Shopping state or semantics.
from shopping_services_fixtures import Group as Group


def spec(root: Path) -> RedditServiceSpec:
    return RedditServiceSpec(
        files=SiteFilesPlan(
            instance_id="reddit-unit",
            workspace_root="/workspace",
            source_path="/workspace/reddit.sif",
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


class Commands:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.calls: list[tuple[str, ...]] = []
        self.error: str | None = None
        self.configure = b"configured"
        self.trusted = b"trusted\n"
        self.health = b"ready"

    def run(self, argv: tuple[str, ...], control: OperationControl) -> bytes:
        control.checkpoint()
        self.calls.append(argv)
        if self.error is not None and self.error in argv:
            raise OSError("injected original native command failure")
        if SEED in argv and "-ec" in argv:
            for name in [
                "postgres",
                "var",
                "tmp",
                "var-tmp",
                "uploads",
                "session",
                "nginx",
                "media-native",
            ]:
                (self.root / "state" / name).mkdir(mode=0o700)
            (self.root / "state/app.env").write_text(
                "APP_SECRET=engineering-not-an-actual-secret\n"
            )
        if INITIALIZE_MEDIA in argv:
            (self.root / "state/media-native/submission_images").mkdir(mode=0o755)
            return b"native-storage-initialized/1"
        if CONFIGURE in argv:
            return self.configure
        if TRUST_ACCOUNT in argv:
            return self.trusted
        if POSTGRES_READY in argv or HTTP_READY in argv:
            return self.health
        return b""
