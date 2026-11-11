"""Observe already-loaded project modules without importing declared plugins."""

import importlib.machinery
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from lab_generate_skill.domain.errors import EvidenceIntegrityError


@dataclass(frozen=True)
class ModuleOrigin:
    name: str
    filename: str
    object_id: int


def observe_project_modules() -> tuple[ModuleOrigin, ...]:
    result: list[ModuleOrigin] = []
    for name, module in tuple(sys.modules.items()):
        # python -m executes the project entry as __main__; use its actual spec
        # identity, then apply exactly the same source/loader checks below.
        if name == "__main__":
            entry_name = getattr(getattr(module, "__spec__", None), "name", None)
            if isinstance(entry_name, str):
                name = entry_name
        if name != "lab_generate_skill" and not name.startswith("lab_generate_skill."):
            continue
        if not isinstance(module, ModuleType):
            raise EvidenceIntegrityError("Project module has no loaded module object")
        filename = getattr(module, "__file__", None)
        spec = getattr(module, "__spec__", None)
        if (
            not isinstance(filename, str)
            or not filename.endswith(".py")
            or spec is None
            or spec.name != name
            or spec.origin != filename
            or type(spec.loader) is not importlib.machinery.SourceFileLoader
            or spec.loader.path != filename
            or getattr(module, "__loader__", None) is not spec.loader
        ):
            raise EvidenceIntegrityError(
                "Project module has inconsistent source origin: " + name
            )
        path = Path(filename)
        expected_suffix = name.replace(".", "/")
        if hasattr(module, "__path__"):
            if (
                not filename.endswith("/" + expected_suffix + "/__init__.py")
                or tuple(module.__path__) != (str(path.parent),)
                or tuple(spec.submodule_search_locations or ()) != (str(path.parent),)
            ):
                raise EvidenceIntegrityError(
                    "Project package has an alternate search path: " + name
                )
        elif not filename.endswith("/" + expected_suffix + ".py"):
            raise EvidenceIntegrityError(
                "Project module name differs from source path: " + name
            )
        result.append(ModuleOrigin(name, filename, id(module)))
    if not any(item.name == "lab_generate_skill" for item in result):
        raise EvidenceIntegrityError("Project package is not loaded")
    if len({item.name for item in result}) != len(result):
        raise EvidenceIntegrityError("Project module has duplicate loaded identities")
    return tuple(sorted(result, key=lambda item: item.name))
