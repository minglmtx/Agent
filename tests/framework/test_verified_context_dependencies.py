"""Finite changed-module boundaries; the pre-existing whole-tree failure stays open."""

from pathlib import Path
import hashlib
import json
import os
from lab_generate_skill.policies.actor_verified_context_qualification import (
    VERIFIED_ACTOR_RUNTIME,
)
from test_dependency_boundaries import project_imports, reject_cycles


def test_verified_context_and_initialization_dependencies_and_cycles() -> None:
    root = Path(__file__).resolve().parents[2]
    allowed = {
        "domain": {"domain"},
        "ports": {"domain", "ports"},
        "policies": {"domain", "ports", "policies"},
        "adapters": {"domain", "ports", "policies", "task_families", "adapters"},
        "application": {"domain", "ports", "policies", "application"},
        "bootstrap": {
            "domain",
            "ports",
            "policies",
            "adapters",
            "runtime",
            "application",
            "registry",
            "release",
            "generator",
            "actor",
            "teacher",
            "sites",
            "bootstrap",
            "evaluators",
        },
    }
    selected = set(VERIFIED_ACTOR_RUNTIME) | {
        "src/lab_generate_skill/policies/actor_prepared_qualification.py",
        "src/lab_generate_skill/policies/actor_verified_context_qualification.py",
    }
    for name in selected:
        path = Path(name)
        layer = path.parts[2]
        package = ".".join(path.with_suffix("").parts[1:-1])
        for imported in project_imports((root / path).read_text(), package):
            assert imported.split(".")[1] in allowed[layer], (name, imported)
    # Cycles through unchanged dependencies still affect newly introduced ports.
    modules = {}
    for path in (root / "src/lab_generate_skill").rglob("*.py"):
        rel = path.relative_to(root / "src").with_suffix("")
        if rel.parts[1] not in set(allowed) | {
            "registry",
            "task_families",
            "evaluators",
            "sites",
            "release",
            "generator",
            "actor",
            "teacher",
            "runtime",
        }:
            continue
        parts = list(rel.parts)
        package = ".".join(parts[:-1])
        if parts[-1] == "__init__":
            parts.pop()
            package = ".".join(parts)
        modules[".".join(parts)] = project_imports(path.read_text(), package)
    graph: dict[str, set[str]] = {}
    for module, imports in modules.items():
        graph[module] = set()
        for name in imports:
            parts = name.split(".")
            while parts and ".".join(parts) not in modules:
                parts.pop()
            dependency = ".".join(parts)
            if dependency in modules and dependency != module:
                graph[module].add(dependency)
    # Preserve the whole-tree failure separately. A pre-existing cycle may be
    # reused only when every member is byte-identical to the accepted baseline
    # and none belongs to this finite change. New/changed cycles still fail.
    baseline = (
        root.parent / "lab-generate-skill-actor-prepared-qualified-candidate-20261107"
    )
    cyclic = cyclic_components(graph)
    selected_modules = {".".join(Path(n).with_suffix("").parts[1:]) for n in selected}
    inherited = []
    for component in cyclic:
        assert not (set(component) & selected_modules), component
        pins = {}
        for module in component:
            relative = Path("src", *module.split(".")).with_suffix(".py")
            if not (root / relative).is_file():
                relative = relative.with_suffix("") / "__init__.py"
            raw = (root / relative).read_bytes()
            assert raw == (baseline / relative).read_bytes(), component
            pins[str(relative)] = hashlib.sha256(raw).hexdigest()
        inherited.append({"modules": component, "unchanged_files": pins})
    excluded = {name for component in cyclic for name in component}
    reject_cycles(
        {
            name: edges - excluded
            for name, edges in graph.items()
            if name not in excluded
        }
    )
    output = os.environ.get("LAB_JOB_OUTPUT_DIRECTORY")
    if output:
        (Path(output) / "inherited-dependency-cycles.json").write_text(
            json.dumps(
                {
                    "finite_changed_modules_passed": True,
                    "whole_tree_gate_passed": False if inherited else True,
                    "unchanged_baseline": str(baseline),
                    "inherited_cycles": inherited,
                },
                indent=2,
            )
            + "\n"
        )


def cyclic_components(graph: dict[str, set[str]]) -> list[list[str]]:
    """Enumerate full strongly connected components, including transitive edges."""
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    active: set[str] = set()
    result: list[list[str]] = []

    def visit(name: str) -> None:
        indices[name] = low[name] = len(indices)
        stack.append(name)
        active.add(name)
        for dependency in sorted(graph[name]):
            if dependency not in indices:
                visit(dependency)
                low[name] = min(low[name], low[dependency])
            elif dependency in active:
                low[name] = min(low[name], indices[dependency])
        if low[name] == indices[name]:
            members = []
            while True:
                node = stack.pop()
                active.remove(node)
                members.append(node)
                if node == name:
                    break
            if len(members) > 1:
                result.append(sorted(members))

    for name in sorted(graph):
        if name not in indices:
            visit(name)
    return sorted(result)
