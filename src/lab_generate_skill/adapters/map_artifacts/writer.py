"""Retain complete/partial native bytes then freeze only the declared inventory.

This is file identity publication, not proof that collection/request/DB work is
complete. Caller must settle/stop native transport before sealing and preserve
its own pending/unknown ledger. No writes or publication retries after failure.
"""

from contextlib import contextmanager
import os
from pathlib import Path
import re
import threading
from collections.abc import Iterator
from lab_generate_skill.domain.map_private_artifact import (
    MapArtifactPlan,
    parse_map_artifact_plan,
    MapArtifactManifest,
    MapArtifactHandle,
)
from lab_generate_skill.domain.release import ReleaseArtifact, ReleaseFile
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.ports.map_private_artifact import MapArtifactAuthority
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.releases.artifact_freeze import FileArtifactFreezer
from lab_generate_skill.adapters.releases.artifact_copy import sync_directory
from .files import private_directory, write_once


class MapArtifactWriter:
    def __init__(
        self,
        plan: MapArtifactPlan,
        workspace: Path,
        authority: MapArtifactAuthority,
    ) -> None:
        self.plan = parse_map_artifact_plan(plan)
        if (
            not isinstance(workspace, Path)
            or str(workspace) != self.plan.workspace_root
            or not callable(getattr(authority, "verify", None))
        ):
            raise ValueError(
                "Trusted workspace and original artifact authority required"
            )
        self.workspace, self.authority = workspace, authority
        self.root = Path(self.plan.private_root)
        self.working = self.root / "working"
        self.published = self.root / "published"
        self.owner = os.getpid()
        self.lock = threading.Lock()
        self.state = "new"
        self.files: list[ReleaseFile] = []
        self.total = 0
        self.names: set[str] = set()
        self.handle: MapArtifactHandle | None = None
        self.last_artifact: ReleaseArtifact | None = None

    @contextmanager
    def exclusive(self, control: OperationControl) -> Iterator[None]:
        if os.getpid() != self.owner:
            raise OwnershipConflict("Private files belong to original worker process")
        while not self.lock.acquire(timeout=min(0.05, control.checkpoint())):
            pass
        try:
            yield
        finally:
            self.lock.release()

    def initialize(self, control: OperationControl) -> None:
        with self.exclusive(control):
            if self.state != "new":
                raise InvalidTransition("Private artifact initialization is once-only")
            self.authority.verify(self.plan, "initialize", control)
            if self.workspace.resolve(strict=True) != self.workspace:
                raise ValueError("Trusted workspace aliases another root")
            private_directory(self.root.parent)
            self.state = "initializing"
            try:
                self.root.mkdir(mode=0o700)
                self.working.mkdir(mode=0o700)
                self.published.mkdir(mode=0o700)
                sync_directory(self.root)
                sync_directory(self.root.parent)
                control.checkpoint()
                self.state = "active"
            except BaseException:
                self.state = "failed"
                raise

    def retain(self, name: str, data: bytes, control: OperationControl) -> ReleaseFile:
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,127}", name) is None
            or not isinstance(data, bytes)
        ):
            raise ValueError("Explicit flat private filename and actual bytes required")
        with self.exclusive(control):
            if self.state != "active":
                raise InvalidTransition("Private collection no longer accepts writes")
            self.authority.verify(self.plan, "write", control)
            if name in self.names:
                raise InvalidTransition("Original filename cannot be written twice")
            if (
                len(self.files) >= self.plan.max_files
                or len(data) > self.plan.max_file_bytes
                or self.total + len(data) > self.plan.max_total_bytes
            ):
                raise ValueError("Explicit complete artifact storage budget exhausted")
            private_directory(self.root)
            private_directory(self.working)
            self.names.add(name)
            try:
                entry = write_once(self.working, name, data, control)
                self.files.append(entry)
                self.total += entry.size_bytes
                return entry
            except BaseException:
                self.state = "failed"
                raise

    def seal(self, control: OperationControl) -> MapArtifactHandle:
        with self.exclusive(control):
            if self.state != "active" or not self.files:
                raise InvalidTransition(
                    "One nonempty original file inventory must be sealed once"
                )
            self.authority.verify(self.plan, "seal", control)
            private_directory(self.root)
            private_directory(self.working)
            private_directory(self.published)
            self.state = "sealing"
            try:
                source = ReleaseArtifact(
                    artifact_id=self.plan.artifact_id,
                    root=str(self.working),
                    files=tuple(self.files),
                )
                artifact = FileArtifactFreezer(self.workspace, self.published).freeze(
                    source, "sealed", control
                )
                # The physical publication name is fixed; logical identity stays
                # the one originally admitted in the plan.
                artifact = artifact.model_copy(
                    update={"artifact_id": self.plan.artifact_id}
                )
                self.last_artifact = artifact
                manifest = MapArtifactManifest(plan=self.plan, artifact=artifact)
                entry = write_once(
                    self.published,
                    "manifest.json",
                    manifest.model_dump_json().encode(),
                    control,
                    readonly=True,
                )
                self.published.chmod(0o555)
                sync_directory(self.published)
                sync_directory(self.root)
                self.handle = MapArtifactHandle(
                    plan_sha256=self.plan.digest, manifest=entry
                )
                control.checkpoint()
                self.state = "sealed"
                return self.handle
            except BaseException:
                self.state = "failed"
                raise
