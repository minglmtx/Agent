"""Selected original frontend cache/PID clearing after its original termination.

The registered owner must authorize restore and stop the browser first. Preserve
compiled Sprockets assets; do not touch public/storage, source, DB, logs or other
/tmp content. Reserve once before deletion; partial/unknown is never replayed.
"""

import json
import os
from pathlib import Path
import stat
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.map_services import MapServiceSpec
from lab_generate_skill.domain.map_frontend_lifecycle import (
    MapFrontendStopped,
    MapFrontendCleared,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.map_artifacts.files import (
    private_directory,
    write_once,
)
from lab_generate_skill.adapters.releases.artifact_copy import sync_directory


def information(path: Path) -> os.stat_result:
    value = path.lstat()
    if (
        path.parent.resolve(strict=True) != path.parent
        or value.st_uid != os.getuid()
        or not (
            stat.S_ISDIR(value.st_mode)
            or stat.S_ISLNK(value.st_mode)
            or stat.S_ISSOCK(value.st_mode)
            or stat.S_ISFIFO(value.st_mode)
            or stat.S_ISREG(value.st_mode)
            and value.st_nlink == 1
        )
    ):
        raise EvidenceIntegrityError(
            "Unexpected original private Map transient identity"
        )
    return value


def removal_tree(
    path: Path, control: OperationControl
) -> list[tuple[Path, os.stat_result]]:
    pending, result = [path], []
    while pending:
        control.checkpoint()
        current = pending.pop()
        value = information(current)
        result.append((current, value))
        if len(result) > 100000:
            raise EvidenceIntegrityError("Original Map transient tree exceeds bound")
        if stat.S_ISDIR(value.st_mode):
            pending.extend(current.iterdir())
    return sorted(result, key=lambda row: len(row[0].parts), reverse=True)


def owned_directory(path: Path) -> None:
    # Rails creates descendants using its umask; a 0755 cache beneath the
    # original private 0700 tmp root is valid. Do not require a different layout.
    if not stat.S_ISDIR(information(path).st_mode):
        raise EvidenceIntegrityError("Original native transient directory required")


def remove_original(
    rows: list[tuple[Path, os.stat_result]], control: OperationControl
) -> None:
    for path, original in rows:
        control.checkpoint()
        now = information(path)
        # Own child deletions change directory timestamps/link counts; exact
        # directory inode/owner/mode still must match. Leaf bytes are not edited.
        if (now.st_dev, now.st_ino, now.st_uid, now.st_mode) != (
            original.st_dev,
            original.st_ino,
            original.st_uid,
            original.st_mode,
        ) or (
            not stat.S_ISDIR(now.st_mode)
            and (now.st_size, now.st_mtime_ns, now.st_ctime_ns, now.st_nlink)
            != (
                original.st_size,
                original.st_mtime_ns,
                original.st_ctime_ns,
                original.st_nlink,
            )
        ):
            raise EvidenceIntegrityError(
                "Original Map transient changed before removal"
            )
        if stat.S_ISDIR(now.st_mode):
            path.rmdir()
        else:
            path.unlink()


class NativeMapFrontendTransients:
    def clear(
        self,
        spec: MapServiceSpec,
        stopped: MapFrontendStopped,
        control: OperationControl,
    ) -> MapFrontendCleared:
        spec = MapServiceSpec.model_validate(spec)
        stopped = MapFrontendStopped.model_validate(stopped)
        node = Path(spec.inputs.files.node_root)
        root = Path(spec.inputs.node_tree("frontend"))
        for path in (node, root, root / "tmp"):
            private_directory(path)
        cache, pids = root / "tmp/cache", root / "tmp/pids"
        selected: list[Path] = []
        preserved: tuple[Path, os.stat_result] | None = None
        if os.path.lexists(cache):
            owned_directory(cache)
            for child in sorted(cache.iterdir()):
                value = information(child)
                if child.name == "assets" and stat.S_ISDIR(value.st_mode):
                    for asset in sorted(child.iterdir()):
                        info = information(asset)
                        if asset.name == "sprockets" and stat.S_ISDIR(info.st_mode):
                            preserved = asset, info
                        else:
                            selected.append(asset)
                else:
                    selected.append(child)
        if os.path.lexists(pids):
            selected.append(pids)
        removals = [removal_tree(path, control) for path in selected]
        control.checkpoint()
        marker = node / f"frontend-reset-{stopped.generation}"
        marker.mkdir(mode=0o700)
        private_directory(marker)
        sync_directory(node)
        intent = dict(
            spec=spec.model_dump(mode="json"),
            stopped=stopped.model_dump(mode="json"),
            removed=[str(p.relative_to(root)) for p in selected],
            preserve_compiled_assets=True,
        )
        write_once(
            marker,
            "intent.json",
            json.dumps(intent, sort_keys=True).encode(),
            control,
            readonly=True,
        )
        for rows in removals:
            remove_original(rows, control)
        cache.mkdir(mode=0o700, exist_ok=True)
        pids.mkdir(mode=0o700)
        for path in (cache, pids):
            owned_directory(path)
        if preserved is not None:
            path, old = preserved
            current = information(path)
            if (
                current.st_dev,
                current.st_ino,
                current.st_mode,
                current.st_mtime_ns,
                current.st_ctime_ns,
            ) != (
                old.st_dev,
                old.st_ino,
                old.st_mode,
                old.st_mtime_ns,
                old.st_ctime_ns,
            ):
                raise EvidenceIntegrityError(
                    "Original compiled asset cache changed during clearing"
                )
        for path in (cache / "assets", cache, pids, root / "tmp"):
            if path.is_dir():
                sync_directory(path)
        result = MapFrontendCleared(
            spec=spec,
            stopped=stopped,
            removed=tuple(str(p.relative_to(root)) for p in selected),
            preserved_sprockets=preserved is not None,
        )
        write_once(
            marker,
            "cleared.json",
            result.model_dump_json().encode(),
            control,
            readonly=True,
        )
        control.checkpoint()
        return result
