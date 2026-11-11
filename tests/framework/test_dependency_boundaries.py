"""Architecture gates for implemented modules, without importing heavy runtimes."""

import ast
import subprocess
import sys
from pathlib import Path
import pytest


def project_imports(source: str, package: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                if node.level > len(parts):
                    raise ValueError("Relative import escapes project package")
                prefix = parts[: len(parts) - node.level + 1]
                if node.module:
                    prefix.extend(node.module.split("."))
                module = ".".join(prefix)
            else:
                module = node.module or ""
            names.add(module)
            names.update(module + "." + alias.name for alias in node.names)
    return {name for name in names if name.startswith("lab_generate_skill.")}


def reject_cycles(graph: dict[str, set[str]]) -> None:
    active: set[str] = set()
    done: set[str] = set()

    def visit(name: str) -> None:
        if name in active:
            raise ValueError("Cyclic project dependency: " + name)
        if name in done:
            return
        active.add(name)
        for dependency in graph[name]:
            visit(dependency)
        active.remove(name)
        done.add(name)

    for name in graph:
        visit(name)


def test_core_imports_do_not_load_legacy_or_heavy_runtime() -> None:
    program = """
import sys
from lab_generate_skill.domain.evaluation import Evaluation
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.ports.evaluator import Evaluator
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.adapters.ledger.resource_journal import FileResourceJournal
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.construction_inputs import GenerationInput
from lab_generate_skill.ports.generation import Generator
from lab_generate_skill.ports.teacher import Teacher
from lab_generate_skill.domain.retrieval import RetrievalResult
from lab_generate_skill.adapters.plans.retrieval_evidence import EvidenceRetrievalRecords
from lab_generate_skill.adapters.retrieval.cpu_encoder import CpuEncoder
from lab_generate_skill.application.admit_candidate import prepare_actor_input
from lab_generate_skill.application.actor_generation import execute_actor_generation
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.actor.response import parse_actor_action
from lab_generate_skill.actor.decisions import RecordedActorDecisions
from lab_generate_skill.application.actor_loop import RecordedActorRunner
from lab_generate_skill.adapters.models.transformers_actor import ResidentActorEngine
from lab_generate_skill.adapters.models.actor_worker_client import SupervisedActorEngine
from lab_generate_skill.bootstrap.actor_worker import main as actor_worker_main
from lab_generate_skill.adapters.models.local_actor import RecordedLocalActorModel
from lab_generate_skill.adapters.models.actor_resource import registered_actor
from lab_generate_skill.adapters.storage.traces import EvidenceTraceRecords
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from lab_generate_skill.adapters.models.paid_sender import LedgerModelSender
from lab_generate_skill.adapters.models.openrouter import OpenRouterTransport
from lab_generate_skill.adapters.models.failure_billing import LedgerFailureBilling
from lab_generate_skill.adapters.ledger.claims import FileSourceClaims
from lab_generate_skill.release.candidates import ReleaseCandidates
from lab_generate_skill.generator.candidates import RecordedGenerator
from lab_generate_skill.application.generator_admission import ConstructionGeneratorAuthority
from lab_generate_skill.application.generator_resource_admission import RunGeneratorResourceAuthority
from lab_generate_skill.bootstrap.generator_resource import bind_generator_resource_authority
from lab_generate_skill.bootstrap.admin_description import load_product_description_inputs
from lab_generate_skill.adapters.plans.generator_admission import EvidenceGeneratorCallInputs
for name in ('torch', 'transformers', 'playwright', 'browsergym',
             'lab_generate_skill.schemas', 'lab_generate_skill.cli'):
    assert name not in sys.modules, name
"""
    subprocess.run([sys.executable, "-B", "-c", program], check=True)


def test_domain_and_ports_import_only_declared_project_layers() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "lab_generate_skill"
    dependencies = {
        "domain": {"domain"},
        "registry": {"domain", "registry"},
        "task_families": {"domain", "task_families"},
        "evaluators": {
            "domain",
            "ports",
            "policies",
            "task_families",
            "evaluators",
            "sites",
        },
        "sites": {"domain", "ports", "policies", "task_families", "sites"},
        "release": {"domain", "ports", "policies", "registry", "release"},
        "generator": {"domain", "ports", "policies", "generator"},
        "actor": {"domain", "ports", "policies", "actor"},
        "teacher": {"domain", "ports", "policies", "teacher"},
        "ports": {"domain", "ports"},
        "runtime": {"domain", "ports", "policies", "runtime"},
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
    modules: dict[str, set[str]] = {}
    for layer, allowed in dependencies.items():
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
            names = project_imports(path.read_text(), package)
            for name in names:
                assert name.split(".")[1] in allowed, (path, name)
                if layer == "evaluators":
                    check_evaluator_import(
                        path.relative_to(root / "evaluators").parts[0], name
                    )
                if layer == "sites":
                    check_site_import(path.relative_to(root / "sites").parts[0], name)
            modules[".".join(parts)] = names
    graph: dict[str, set[str]] = {}
    for module, imports in modules.items():
        graph[module] = set()
        for imported in imports:
            parts = imported.split(".")
            while parts and ".".join(parts) not in modules:
                parts.pop()
            target = ".".join(parts)
            if target in modules and target != module:
                graph[module].add(target)
    reject_cycles(graph)


@pytest.mark.parametrize(
    "source",
    [
        "import lab_generate_skill.adapters.clock",
        "from lab_generate_skill import adapters",
        "from ..adapters import clock",
    ],
)
def test_layer_check_resolves_package_alias_and_relative_imports(source: str) -> None:
    names = project_imports(source, "lab_generate_skill.application")
    assert any(name.split(".")[1] == "adapters" for name in names)


def test_cycle_check_rejects_indirect_cycle_but_accepts_shared_dependency() -> None:
    reject_cycles({"a": {"c"}, "b": {"c"}, "c": set()})
    with pytest.raises(ValueError, match="Cyclic"):
        reject_cycles({"a": {"b"}, "b": {"c"}, "c": {"a"}})


def check_site_import(site: str, name: str) -> None:
    parts = name.split(".")
    if len(parts) >= 3 and parts[:2] == ["lab_generate_skill", "sites"]:
        if parts[2] != site:
            raise ValueError("Website implementations must not import another site")


@pytest.mark.parametrize(
    "source",
    [
        "from lab_generate_skill.sites import shopping",
        "import lab_generate_skill.sites.reddit.tasks",
        "from ..shopping import tasks",
    ],
)
def test_site_boundary_rejects_cross_site_imports(source: str) -> None:
    names = project_imports(source, "lab_generate_skill.sites.shopping_admin")
    with pytest.raises(ValueError, match="another site"):
        for name in names:
            check_site_import("shopping_admin", name)


def check_evaluator_import(site: str, name: str) -> None:
    if name.startswith("lab_generate_skill.sites."):
        expected = "lab_generate_skill.sites." + site + ".evidence_schema"
        if name != expected and not name.startswith(expected + "."):
            raise ValueError("Evaluator may import only its own pure evidence_schema")


@pytest.mark.parametrize(
    "name",
    [
        "lab_generate_skill.sites.shopping_admin.page_capture",
        "lab_generate_skill.sites.reddit.evidence_schema",
        "lab_generate_skill.sites.shopping_admin.tasks.product_execution",
    ],
)
def test_evaluator_cannot_import_site_operations_or_another_site(name: str) -> None:
    with pytest.raises(ValueError):
        check_evaluator_import("shopping_admin", name)
    check_evaluator_import(
        "shopping_admin",
        "lab_generate_skill.sites.shopping_admin.evidence_schema.AdminPageHealth",
    )
