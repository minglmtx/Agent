"""Pinned original producer material at the existing business entry boundary.

Loading immutable declarations gives no namespace, owner, claim or replay right.
The existing controlled source consumers must perform all original live gates.
"""

from pathlib import Path
from typing import TypeVar
from lab_generate_skill.adapters.map_runtime.metadata import (
    read_pinned_bytes,
    object_json,
)
from lab_generate_skill.adapters.plans.closed_source_protocol import decode_command
from lab_generate_skill.domain.closed_source_read import (
    ClosedAdminNavigationReadMaterial,
    ClosedMapReadMaterial,
)
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.lifecycle import OperationControl

Material = TypeVar("Material", ClosedAdminNavigationReadMaterial, ClosedMapReadMaterial)


def load_source_material(
    path: Path,
    sha256: str,
    expected: type[Material],
    workspace: Path,
    control: OperationControl,
) -> Material:
    """Read once, accept actual standalone declarations or the original request.

    The request's historical scope/configuration is data only and is never used
    to open a store, select an interpreter or replace the current caller.
    """
    control.checkpoint()
    if expected not in (ClosedAdminNavigationReadMaterial, ClosedMapReadMaterial):
        raise TypeError("Explicit compiled Admin or Map source material type required")
    if (
        not isinstance(path, Path)
        or not isinstance(workspace, Path)
        or not path.is_absolute()
        or not workspace.is_absolute()
        or workspace.resolve(strict=True) != workspace
        or not path.is_relative_to(workspace)
        or path.resolve(strict=True) != path
    ):
        raise ValueError("Original canonical workspace source input required")
    raw = read_pinned_bytes(
        path,
        ReleaseFile(
            path=path.name,
            sha256=sha256,
            size_bytes=path.stat().st_size,
            executable=False,
        ),
        control,
    )
    value = object_json(raw)
    if value.get("schema_version") == "closed-source-read-command/1":
        material = decode_command(raw).material
        if not isinstance(material, expected):
            raise ValueError("Original source input belongs to another compiled site")
        result = expected.model_validate(material)
    else:
        # The original Map closed-declarations producer omits the default schema
        # field. Exact expected-model validation still rejects extra/wrong fields.
        if (
            expected is ClosedAdminNavigationReadMaterial
            and value.get("schema_version") != "closed-admin-navigation-read-material/1"
        ):
            raise ValueError("Explicit original Admin source material version required")
        result = expected.model_validate_json(raw)
    if result.site.configuration.files.workspace_root != str(workspace):
        raise ValueError("Original source material left selected workspace")
    control.checkpoint()
    return result
