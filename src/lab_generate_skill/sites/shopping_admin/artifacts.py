"""Restore the declared Admin file scope, not a complete website baseline.

Inputs: validated original layout/snapshot, original OperationControl. Output:
verified snapshot descriptor. No database/cache reset, authority, service start,
retry, rollback or resource cleanup here. Parent must persist descriptors and
pre-register resources before effects, stop writers and supervise this worker.
Partial save/restore keeps original errors and remaining files for diagnosis;
no successful result means the instance must remain isolated until reconciled.
"""

from pathlib import Path
from lab_generate_skill.ports.lifecycle import OperationControl
from .artifact_contract import AdminArtifactLayout, AdminArtifactSnapshot
from .artifact_io import checked_path
from .artifact_tree import copy_tree, remove_tree, tree_digest


class AdminArtifacts:
    def __init__(self, layout: AdminArtifactLayout) -> None:
        self.layout = AdminArtifactLayout.model_validate(layout)
        self.app = Path(self.layout.app_root)
        self.backup = Path(self.layout.backup_root)

    def _roots(self, control: OperationControl) -> None:
        control.checkpoint()
        for path in (Path(self.layout.node_root), self.app, self.backup):
            checked_path(path, control)
        if not self.app.is_dir() or not self.backup.parent.is_dir():
            raise ValueError("Original application and backup parent must exist")

    def save(self, control: OperationControl) -> AdminArtifactSnapshot:
        self._roots(control)
        digests = tuple(tree_digest(self.app / p, control) for p in self.layout.paths)
        control.checkpoint()
        self.backup.mkdir(mode=0o700)  # exclusive: never overwrite/retry a snapshot
        for index, (relative, expected) in enumerate(
            zip(self.layout.paths, digests, strict=True)
        ):
            source, dest = self.app / relative, self.backup / str(index)
            if expected is not None:
                copy_tree(source, dest, control)
            if (
                tree_digest(dest, control) != expected
                or tree_digest(source, control) != expected
            ):
                raise ValueError("Artifact changed while saving baseline")
        control.checkpoint()
        return AdminArtifactSnapshot(layout=self.layout, tree_sha256=digests)

    def verify(
        self, snapshot: AdminArtifactSnapshot, control: OperationControl
    ) -> AdminArtifactSnapshot:
        snapshot = AdminArtifactSnapshot.model_validate(snapshot)
        if snapshot.layout != self.layout:
            raise ValueError(
                "Artifact restore must use the exact original instance and scope"
            )
        self._roots(control)
        if not self.backup.is_dir():
            raise ValueError("Original artifact backup is missing")
        # Preflight every source/target before changing any target.
        expected_names = {
            str(i)
            for i, digest in enumerate(snapshot.tree_sha256)
            if digest is not None
        }
        if {p.name for p in self.backup.iterdir()} != expected_names:
            raise ValueError("Artifact backup entries differ from original snapshot")
        for index, (relative, expected) in enumerate(
            zip(self.layout.paths, snapshot.tree_sha256, strict=True)
        ):
            if tree_digest(self.backup / str(index), control) != expected:
                raise ValueError("Artifact backup integrity mismatch")
            tree_digest(self.app / relative, control)
        control.checkpoint()
        return snapshot

    def restore(
        self, snapshot: AdminArtifactSnapshot, control: OperationControl
    ) -> AdminArtifactSnapshot:
        snapshot = self.verify(snapshot, control)
        for index, (relative, expected) in enumerate(
            zip(self.layout.paths, snapshot.tree_sha256, strict=True)
        ):
            target = self.app / relative
            remove_tree(target, control)
            if expected is not None:
                control.checkpoint()
                target.parent.mkdir(parents=True, exist_ok=True)
                copy_tree(self.backup / str(index), target, control)
            if tree_digest(target, control) != expected:
                raise ValueError("Artifact restored state differs from baseline")
        control.checkpoint()
        return snapshot
