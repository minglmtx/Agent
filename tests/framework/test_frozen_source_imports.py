"""New frozen-source modules retain the existing lightweight import boundary."""

import subprocess
import sys


def test_frozen_source_imports_keep_native_and_model_runtimes_lazy() -> None:
    program = """
import sys
from lab_generate_skill.domain.frozen_execution_origin import FrozenExecutionOrigin
from lab_generate_skill.adapters.plans.stage_validation_source import SupervisedStageValidationContexts
for name in ('torch', 'transformers', 'playwright', 'browsergym',
             'lab_generate_skill.schemas', 'lab_generate_skill.cli'):
    assert name not in sys.modules, name
"""
    subprocess.run([sys.executable, "-B", "-c", program], check=True)


def test_changed_frozen_source_layers_and_reachable_cycles() -> None:
    from pathlib import Path
    from test_dependency_boundaries import project_imports, reject_cycles

    root = Path(__file__).resolve().parents[2] / "src" / "lab_generate_skill"
    changed = {
        "domain.frozen_execution_origin",
        "domain.execution_task_source",
        "domain.task_execution",
        "domain.actor_admission",
        "ports.source_stage_validation",
        "adapters.plans.execution_task_source",
        "adapters.plans.closed_source_records",
        "adapters.plans.closed_source_transport",
        "adapters.plans.stage_validation_source",
        "bootstrap.execution_task_source",
        "bootstrap.closed_map_source_read",
    }
    allowed = {
        "domain": {"domain"},
        "ports": {"domain", "ports"},
        "adapters": {"domain", "ports", "policies", "task_families", "adapters"},
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
    layers = (
        "domain",
        "registry",
        "task_families",
        "evaluators",
        "sites",
        "release",
        "generator",
        "actor",
        "teacher",
        "ports",
        "runtime",
        "adapters",
        "application",
        "bootstrap",
    )
    modules = {}
    for layer in layers:
        for path in (root / layer).rglob("*.py"):
            parts = [
                "lab_generate_skill",
                *path.relative_to(root).with_suffix("").parts,
            ]
            if parts[-1] == "__init__":
                parts.pop()
                package = ".".join(parts)
            else:
                package = ".".join(parts[:-1])
            imports = project_imports(path.read_text(), package)
            name = ".".join(parts)
            modules[name] = imports
            relative = name.removeprefix("lab_generate_skill.")
            if relative in changed:
                assert all(item.split(".")[1] in allowed[layer] for item in imports), (
                    path,
                    imports,
                )
    starts = {"lab_generate_skill." + name for name in changed}
    assert starts <= set(modules)
    graph: dict[str, set[str]] = {}
    for name, imports in modules.items():
        graph[name] = set()
        for imported in imports:
            parts = imported.split(".")
            while parts and ".".join(parts) not in modules:
                parts.pop()
            resolved = ".".join(parts)
            if resolved in modules and resolved != name:
                graph[name].add(resolved)
    reachable = set()
    pending = list(starts)
    while pending:
        name = pending.pop()
        if name not in reachable:
            reachable.add(name)
            pending.extend(graph[name] - reachable)
    reject_cycles({name: graph[name] for name in reachable})
