"""One reserved private frontend rewrite; retain originals and every partial state.

The original acquired worker owns this node root. No legacy lookup or shared
source mutation; original publication and clone pins are verified again at apply.
"""

import os
from pathlib import Path
import stat
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.map_services import MapServiceSpec
from lab_generate_skill.domain.map_frontend import (
    FRONTEND_FILES,
    MapFrontendPlan,
    MapFrontendPrepared,
)
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.map_artifacts.files import (
    private_directory,
    write_once,
)
from lab_generate_skill.adapters.releases.artifact_copy import (
    sync_directory,
    sync_regular_file,
)
from .metadata import read_pinned_bytes
from .read_inputs import PublishedMapInputs


def identity(path: Path) -> tuple[int, int, int, int, int, int]:
    value = path.lstat()
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_nlink != 1
        or value.st_uid != os.getuid()
    ):
        raise EvidenceIntegrityError(
            "Original independent owned frontend file required"
        )
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
        value.st_mode,
    )


def read_source(root: Path, pin: ReleaseFile, control: OperationControl) -> bytes:
    path = root / pin.path
    leaf = ReleaseFile.model_validate({**pin.model_dump(), "path": path.name})
    return read_pinned_bytes(path, leaf, control)


class NativeMapFrontendFiles:
    def _pins(
        self, spec: MapServiceSpec, control: OperationControl
    ) -> tuple[ReleaseFile, ...]:
        private_directory(Path(spec.inputs.files.node_root))
        private_directory(Path(spec.inputs.node_tree("frontend")))
        inventory = next(
            i
            for i in PublishedMapInputs().read(spec.inputs, control)
            if i.role == "frontend"
        )
        pins = tuple(
            sorted(
                (m.file for m in inventory.files if m.file.path in FRONTEND_FILES),
                key=lambda f: f.path,
            )
        )
        if {p.path for p in pins} != FRONTEND_FILES or any(
            p.executable or not 0 < p.size_bytes <= 1024 * 1024 for p in pins
        ):
            raise EvidenceIntegrityError(
                "Complete original published frontend inputs required"
            )
        return pins

    def read(self, spec: MapServiceSpec, control: OperationControl) -> dict[str, bytes]:
        spec = MapServiceSpec.model_validate(spec)
        root = Path(spec.inputs.node_tree("frontend"))
        return {
            p.path: read_source(root, p, control) for p in self._pins(spec, control)
        }

    def apply(
        self, plan: MapFrontendPlan, control: OperationControl
    ) -> MapFrontendPrepared:
        plan = MapFrontendPlan.model_validate(plan)
        control.checkpoint()
        marker = Path(plan.marker)
        if os.path.lexists(marker):
            raise FileExistsError(
                "Frontend preparation already attempted; retain original marker"
            )
        if self._pins(plan.spec, control) != plan.original:
            raise EvidenceIntegrityError(
                "Frontend plan changed original publication inventory"
            )
        root = Path(plan.spec.inputs.node_tree("frontend"))
        originals = {}
        identities = {}
        for pin in plan.original:
            path = root / pin.path
            before = identity(path)
            originals[pin.path] = read_source(root, pin, control)
            if before != identity(path):
                raise EvidenceIntegrityError(
                    "Frontend source changed during preparation read"
                )
            identities[pin.path] = before
        if any(
            os.path.lexists(root / name)
            for name in ("log", "tmp", "storage", "node_modules")
        ):
            raise EvidenceIntegrityError(
                "Original freshly staged frontend transients must be absent"
            )
        control.checkpoint()
        marker.mkdir(
            mode=0o700
        )  # exclusive durable attempt; never resume a partial write
        private_directory(marker)
        sync_directory(marker.parent)
        write_once(
            marker,
            "intent.json",
            plan.model_dump_json().encode(),
            control,
            readonly=True,
        )
        for index, pin in enumerate(plan.original):
            write_once(
                marker,
                f"original-{index:02d}",
                originals[pin.path],
                control,
                readonly=True,
            )
        for index, change in enumerate(plan.changes):
            replacement = marker / f"replacement-{index:02d}"
            write_once(marker, replacement.name, change.content, control)
            replacement.chmod(stat.S_IMODE(identities[change.original.path][-1]))
            sync_regular_file(replacement)
        for name in ("log", "tmp", "storage"):
            control.checkpoint()
            (root / name).mkdir(mode=0o700)
        for index, change in enumerate(plan.changes):
            path = root / change.original.path
            control.checkpoint()
            if (
                path.parent.resolve(strict=True) != path.parent
                or identity(path) != identities[change.original.path]
            ):
                raise EvidenceIntegrityError(
                    "Original frontend file changed before private replacement"
                )
            os.replace(marker / f"replacement-{index:02d}", path)
            sync_directory(path.parent)
            sync_directory(marker)
            control.checkpoint()
        after = {p.path: p for p in plan.original}
        after.update({c.original.path: c.after() for c in plan.changes})
        for pin in after.values():
            read_source(root, pin, control)
        for name in ("log", "tmp", "storage"):
            private_directory(root / name)
            if any((root / name).iterdir()):
                raise EvidenceIntegrityError(
                    "Frontend transient directory changed before startup"
                )
        sync_directory(root)
        receipt = MapFrontendPrepared(
            preparation_sha256=plan.sha256(),
            original=plan.original,
            changed=tuple(c.after() for c in plan.changes),
        )
        raw = receipt.model_dump_json().encode()
        saved = write_once(marker, "prepared.json", raw, control, readonly=True)
        if read_pinned_bytes(marker / saved.path, saved, control) != raw:
            raise EvidenceIntegrityError(
                "Frontend preparation receipt readback differs"
            )
        receipt.check(plan)
        return receipt
