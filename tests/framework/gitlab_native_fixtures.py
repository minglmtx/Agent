"""Synthetic original native effects; no database, service or real authority."""

from pathlib import Path
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.gitlab.service_contract import (
    GitlabServiceSpec,
    GitlabPorts,
)
from lab_generate_skill.sites.gitlab.service_programs import (
    CONFIGURE,
    SEED,
    POSTGRES_READY,
    BACKEND_READY,
    HTTP_READY,
)
from lab_generate_skill.sites.gitlab.snapshot_programs import (
    INVENTORY,
    CLEAR_SOCKETS,
    SOCKET_PATHS,
)
from lab_generate_skill.sites.gitlab.snapshot import GitlabInventory, StoppedSockets

# This existing fixture implements only generic original NativeServices pins/
# exits. No Shopping service names/configuration/state are used for GitLab.
from shopping_services_fixtures import Group as Group


def plan(root: Path) -> SiteFilesPlan:
    return SiteFilesPlan(
        instance_id="gitlab-unit",
        workspace_root="/workspace",
        source_path="/workspace/gitlab.sif",
        node_root=str(root),
        image=ReleaseFile(
            path="gitlab.sif", size_bytes=1, sha256="a" * 64, executable=False
        ),
    )


def spec(root: Path) -> GitlabServiceSpec:
    return GitlabServiceSpec(
        files=plan(root),
        ports=GitlabPorts(web=12001, metrics=12002),
        database_peer_user="native_user",
    )


class Commands:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.calls: list[tuple[str, ...]] = []
        self.error: str | None = None
        self.failure: BaseException = OSError("injected native failure")
        self.health = b"ready"
        self.noexec_reply = b""
        self.preflight_writes = False
        self.inventory = GitlabInventory(
            sha256="b" * 64, files=1, directories=4, bytes=10, symlinks=1
        )
        self.scans: list[GitlabInventory] = []
        self.sockets = StoppedSockets(removed=(), absent=SOCKET_PATHS)

    def run(self, argv: tuple[str, ...], control: OperationControl) -> bytes:
        control.checkpoint()
        self.calls.append(argv)
        if self.error is not None and self.error in argv:
            raise self.failure
        if "/control/noexec-check.sh" in argv:
            return self.noexec_reply
        if "-n" in argv:
            if self.preflight_writes and "/control/seed.sh" in argv:
                (self.root / "state/unexpected").write_text("not just compilation")
            return b""
        if "/control/seed.sh" in argv:
            (self.root / "state/original").write_text("native bytes")
        if CONFIGURE in argv and argv[-1] != CONFIGURE:
            return b"configured"
        if any(p in argv and argv[-1] != p for p in (BACKEND_READY, HTTP_READY)) or (
            "/control/postgres-ready.sh" in argv
        ):
            return self.health
        if INVENTORY in argv:
            value = (
                self.scans.pop(0)
                if self.scans and "clear" not in argv
                else self.inventory
            )
            return value.model_dump_json().encode()
        if CLEAR_SOCKETS in argv:
            return self.sockets.model_dump_json().encode()
        return b"Syntax OK\n"


class Files:
    def stage(self, value: SiteFilesPlan, control: OperationControl) -> None:
        control.checkpoint()
        root = Path(value.node_root)
        root.mkdir(mode=0o700)
        for name in ("state", "logs", "image"):
            (root / name).mkdir()


class Lease:
    ports = (12001, 12002)

    def release(self, control: OperationControl) -> None:
        raise AssertionError("Only outer original resource may release ports")


class Ports:
    def reserve(self, count: int, control: OperationControl) -> Lease:
        assert count == 2
        control.checkpoint()
        return Lease()
