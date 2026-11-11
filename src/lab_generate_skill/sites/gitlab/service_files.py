"""Immutable private wrapper files; native state remains in the owned tree."""

from pathlib import Path
import stat
from lab_generate_skill.ports.lifecycle import OperationControl
from .service_contract import GitlabServiceSpec
from .service_programs import SERVICE_WRAPPER, SEED, POSTGRES_READY


def checked(path: Path, control: OperationControl) -> None:
    for part in (*reversed(path.parents), path):
        control.checkpoint()
        try:
            mode = part.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode) or (part != path and not stat.S_ISDIR(mode)):
            raise ValueError("Unsafe original private GitLab control path")


def write_controls(spec: GitlabServiceSpec, control: OperationControl) -> None:
    for name, program in (
        ("service.sh", SERVICE_WRAPPER),
        ("seed.sh", SEED),
        ("postgres-ready.sh", POSTGRES_READY),
        ("noexec-check.sh", "printf native_noexec_marker\n"),
    ):
        path = Path(spec.control_root) / name
        checked(path, control)
        with path.open("x") as stream:
            stream.write(program)
        path.chmod(0o600)
    control.checkpoint()
