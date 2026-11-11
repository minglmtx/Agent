"""Test child only: exercise observed origins without production failpoint flags."""

import json
import sys
import time
import importlib.util
from collections import Counter
from types import ModuleType
from dataclasses import asdict
from pathlib import Path

from lab_generate_skill.adapters.releases import installed_sources as gate
from lab_generate_skill.adapters.releases.module_origins import (
    ModuleOrigin,
    observe_project_modules,
)
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.domain.release import ReleaseManifest
from lab_generate_skill.adapters.releases.installed_files import InstalledFileTraversal


class Control:
    def __init__(self) -> None:
        self.deadline = time.monotonic() + 20

    def checkpoint(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise OperationStopped(
                "test source check expired", "unit-installed-sources"
            )
        return remaining

    def wait(self, seconds: float) -> None:
        time.sleep(min(seconds, self.checkpoint()))


def main() -> None:
    manifest = ReleaseManifest.model_validate_json(Path(sys.argv[1]).read_bytes())
    workspace = Path(sys.argv[2])
    fault = sys.argv[3]
    control = Control()
    if fault == "cancelled":
        control.deadline = 0
    if fault == "alternate_path":
        sys.modules["lab_generate_skill"].__path__.append("/old/source")
    if fault == "inconsistent_origin":
        sys.modules["lab_generate_skill"].__file__ = (
            "/old/lab_generate_skill/__init__.py"
        )
    if fault == "main_origin":
        entry = sys.modules["__main__"]
        entry.__spec__ = importlib.util.spec_from_file_location(
            "lab_generate_skill.bootstrap.generator_worker",
            "/old/lab_generate_skill/bootstrap/generator_worker.py",
        )
        # Original __file__/__loader__ disagree with the claimed project spec.
    if fault == "duplicate_main":
        entry = sys.modules["__main__"]
        package = sys.modules["lab_generate_skill"]
        entry.__spec__ = package.__spec__
        entry.__file__ = package.__file__
        entry.__loader__ = package.__loader__
        entry.__path__ = package.__path__
    if fault == "foreign_module":
        foreign = ModuleType("lab_generate_skill.old_component")
        foreign.__file__ = "/old/lab_generate_skill/old_component.py"
        foreign.__spec__ = importlib.util.spec_from_file_location(
            foreign.__name__, foreign.__file__
        )
        assert foreign.__spec__ is not None
        foreign.__loader__ = foreign.__spec__.loader
        sys.modules[foreign.__name__] = foreign
    if fault == "foreign_pinned_module":
        artifact = next(a for a in manifest.artifacts if a.artifact_id == "extra-code")
        filename = Path(artifact.root) / "lab_generate_skill" / "old_component.py"
        spec = importlib.util.spec_from_file_location(
            "lab_generate_skill.old_component", filename
        )
        assert spec is not None and spec.loader is not None
        extra = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(extra)
        sys.modules[extra.__name__] = extra
    if fault in ("late_import", "late_loaded_source_change"):
        original = observe_project_modules
        calls = 0

        def observed() -> tuple[ModuleOrigin, ...]:
            nonlocal calls
            calls += 1
            if calls == 2:
                if fault == "late_import":
                    import lab_generate_skill.domain.optional_policies  # noqa: F401
                else:
                    filename = sys.modules["lab_generate_skill"].__file__
                    assert isinstance(filename, str)
                    target = Path(filename)
                    target.chmod(0o644)
                    target.write_bytes(
                        target.read_bytes() + b"\n# unit late source change\n"
                    )
                    target.chmod(0o444)
            return original()

        setattr(gate, "observe_project_modules", observed)
    counts: Counter[str] = Counter()
    if fault == "hash_counts":
        verify = InstalledFileTraversal.verify

        def counted(self: InstalledFileTraversal, path: Path) -> None:
            counts[str(path)] += 1
            verify(self, path)

        setattr(InstalledFileTraversal, "verify", counted)
    first = gate.verify_installed_sources(manifest, workspace, control)
    first_counts = dict(counts)
    counts.clear()
    second = gate.verify_installed_sources(manifest, workspace, control)
    assert first == second
    if fault == "hash_counts":
        assert first_counts == dict(counts)
        code = manifest.artifacts[0]
        package_files = [
            f for f in code.files if f.path.startswith("lab_generate_skill/")
        ]
        print(
            json.dumps(
                {
                    "sources": asdict(first),
                    "all_code_hashed_each_call": all(
                        str(Path(code.root) / f.path) in first_counts
                        for f in code.files
                    ),
                    "package_files": len(package_files),
                    "package_hash_call_counts": sorted(
                        {
                            first_counts[str(Path(code.root) / f.path)]
                            for f in package_files
                        }
                    ),
                    "executable_hash_calls": first_counts[str(Path(sys.executable))],
                    "metadata_hash_calls": {
                        name: [
                            v
                            for p, v in first_counts.items()
                            if p.endswith(".dist-info/" + name)
                        ]
                        for name in ("METADATA", "WHEEL", "RECORD")
                    },
                    "second_call_repeated_all_hashes": True,
                }
            )
        )
    else:
        print(json.dumps(asdict(first)))


if __name__ == "__main__":
    main()
