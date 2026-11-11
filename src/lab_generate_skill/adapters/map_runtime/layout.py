"""Create selected native controls after complete staging, never initialize a DB.

Original worker acquisition and complete staging precede this leaf. No aliases,
legacy roots, deletion of shared inputs or implicit reuse of partial controls.
"""

import os
from pathlib import Path
import stat
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.map_runtime_inputs import MapTreeRole
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.map_services import MapServiceSpec
from lab_generate_skill.adapters.releases.artifact_copy import (
    sync_regular_file,
    sync_directory,
)
from .read_inputs import PublishedMapInputs
from .metadata import read_pinned_bytes, object_json


def baseline(spec: MapServiceSpec, control: OperationControl) -> dict[str, object]:
    spec = MapServiceSpec.model_validate(spec)
    inventories = {i.role: i for i in PublishedMapInputs().read(spec.inputs, control)}

    def read(role: MapTreeRole, name: str) -> bytes:
        inventory = inventories[role]
        pin = next(m.file for m in inventory.files if m.file.path == name)
        root = Path(spec.inputs.files.node_root) / "input" / role
        leaf_pin = ReleaseFile.model_validate(
            {**pin.model_dump(), "path": Path(name).name}
        )
        return read_pinned_bytes(root / name, leaf_pin, control)

    versions: tuple[tuple[MapTreeRole, str], ...] = (
        ("app", "11"),
        ("search", "14"),
        ("tiles", "15"),
    )
    for role, version in versions:
        if read(role, "postgres/PG_VERSION").decode("ascii").strip() != version:
            raise EvidenceIntegrityError(
                "Original native PostgreSQL snapshot version differs"
            )
    root = Path(spec.inputs.node_tree("app"))
    if os.path.lexists(root / "postgres/postmaster.pid"):
        raise EvidenceIntegrityError(
            "Full original application baseline must be offline"
        )
    value = object_json(read("app", "baseline.json"))
    if (
        value.get("status") != "complete"
        or value.get("full_snapshot_imported") is not True
        or value.get("postgres_version") != "11"
    ):
        raise EvidenceIntegrityError("Complete original geographic baseline required")
    checks = value.get("object_checks")
    if type(checks) is not dict:
        raise EvidenceIntegrityError("Original object page checks required")
    for kind in ("node", "way"):
        check = checks.get(kind)
        if (
            type(check) is not dict
            or check.get("http_status") != 200
            or not check.get("has_object_id")
            or not check.get("id")
        ):
            raise EvidenceIntegrityError(
                "Original native object page validation incomplete"
            )
    return value


def prepare_layout(
    spec: MapServiceSpec, content: dict[str, str], control: OperationControl
) -> tuple[str, ...]:
    spec = MapServiceSpec.model_validate(spec)
    names = {
        "search/hosts",
        "tiles/hosts",
        "frontend/hosts",
        "search/postgresql.conf",
        "tiles/postgresql.conf",
        "search/pg_hba.conf",
        "tiles/pg_hba.conf",
        "search/project/.env",
        "search/project/router.php",
        "tiles/renderd.conf",
        "tiles/apache.conf",
        "frontend/database.yml",
        "frontend/settings.local.yml",
    }
    if (
        type(content) is not dict
        or set(content) != names
        or any(
            type(v) is not str
            or not v
            or len(v.encode("utf-8")) > 1024 * 1024
            or "\0" in v
            for v in content.values()
        )
    ):
        raise ValueError("Complete fixed native service control file set required")
    baseline(spec, control)
    root = Path(spec.inputs.files.state_root)
    control.checkpoint()
    if root.resolve(strict=True) != root or not root.is_dir() or any(root.iterdir()):
        raise EvidenceIntegrityError(
            "Fresh original private Map state directory required"
        )
    info = root.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise EvidenceIntegrityError("Private Map state ownership/mode differs")
    # Exclusive first directory reserves this attempt before any mutation of
    # cloned PIDs. A cancelled/partial preparation cannot be repeated.
    for service, children in (
        ("search", ("run", "tmp", "project", "postgres")),
        ("tiles", ("run", "tmp", "tiles", "log", "postgres")),
        ("frontend", ("run", "tmp", "project", "pg", "app")),
    ):
        control.checkpoint()
        parent = root / service
        parent.mkdir(mode=0o700)
        for child in children:
            (parent / child).mkdir(mode=0o700)
    removed = []
    for role in ("search", "tiles"):
        path = Path(spec.inputs.node_tree(role)) / "postgres/postmaster.pid"
        control.checkpoint()
        if os.path.lexists(path):
            if path.resolve(strict=True) != path or not stat.S_ISREG(
                path.lstat().st_mode
            ):
                raise EvidenceIntegrityError(
                    "Only the private regular cloned PID may be removed"
                )
            path.unlink()
            sync_directory(path.parent)
            removed.append(str(path))
    for name, body in content.items():
        control.checkpoint()
        path = root / name
        with path.open("x", encoding="utf-8") as stream:
            stream.write(body)
        path.chmod(0o600)
        sync_regular_file(path)
    for path in (
        root / "search/project",
        root / "search",
        root / "tiles",
        root / "frontend",
        root,
    ):
        sync_directory(path)
    control.checkpoint()
    return tuple(removed)


class NativeMapLayout:
    def prepare(
        self, spec: MapServiceSpec, content: dict[str, str], control: OperationControl
    ) -> tuple[str, ...]:
        return prepare_layout(spec, content, control)
