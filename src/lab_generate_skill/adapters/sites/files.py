"""Stage pinned site assets using the existing checked release file copier.

No legacy path lookup, symlink fallback, shared mutable cache or implicit cleanup.
Partial roots survive failure for original-owner inspection/cleanup. The outer
worker supervisor supplies the hard I/O boundary and acquisition authority.
"""

import os
from pathlib import Path
import stat
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.releases.artifact_copy import (
    copy_pinned_file,
    sync_directory,
)


class NodeSiteFiles:
    def stage(self, plan: SiteFilesPlan, control: OperationControl) -> None:
        plan = SiteFilesPlan.model_validate(plan)
        self.prepare(plan, control)
        source, root = Path(plan.source_path), Path(plan.node_root)
        copy_pinned_file(source.parent, root / "image", plan.image, control)
        sync_directory(root / "image")
        sync_directory(root)
        control.checkpoint()

    def prepare(self, plan: SiteFilesPlan, control: OperationControl) -> None:
        """Create only this acquisition's exclusive directories, without an image."""
        plan = SiteFilesPlan.model_validate(plan)
        control.checkpoint()
        workspace, source, root = map(
            Path, (plan.workspace_root, plan.source_path, plan.node_root)
        )
        for path in (workspace, source, root.parent):
            if path.resolve(strict=True) != path:
                raise EvidenceIntegrityError("Site staging path uses an alias")
        control.checkpoint()
        root.mkdir(mode=0o700)  # no exist_ok: previous/unknown acquisition retained
        info = root.lstat()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise EvidenceIntegrityError("Private site root ownership/mode mismatch")
        control.checkpoint()
        for child in ("image", "state", "logs"):
            (root / child).mkdir(mode=0o700)
            control.checkpoint()
