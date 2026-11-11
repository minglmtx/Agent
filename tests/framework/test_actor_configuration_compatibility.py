"""Exact original inference pins and limited configuration-only extraction."""

import ast
import hashlib
import json
from pathlib import Path
import pytest
from lab_generate_skill.bootstrap.actor_deployment import (
    ACTOR64_CONFIGURATION_EXTRACTION,
    ACTOR64_CONFIGURATION_ORIGINALS,
    ACTOR64_RUNTIME_FILES,
    ACTOR64_RUNTIME_PINS_SHA256,
)
from lab_generate_skill.policies.actor_prepared_qualification import (
    PREPARED_ACTOR_RUNTIME,
    qualified_prepared_runtime_pins,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from test_actor_deployment_defaults import documents, select

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parents[1]
ORIGINAL = (
    WORKSPACE
    / "experiments/framework-map-navigation42-production-20261102-v1/deployment-4900890/deployment.json"
)


def dump(value: ast.AST) -> str:
    return ast.dump(value, include_attributes=False)


def test_declared_configuration_and_prepared_deltas_keep_other_runtime_bytes() -> None:
    actual = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in (
            *ACTOR64_RUNTIME_FILES,
            *PREPARED_ACTOR_RUNTIME,
            "src/lab_generate_skill/domain/actor_configuration.py",
        )
    }
    assert all(
        actual[name] == value
        for name, value in ACTOR64_CONFIGURATION_EXTRACTION.items()
    )
    normalized = {name: actual[name] for name in ACTOR64_RUNTIME_FILES}
    normalized = qualified_prepared_runtime_pins(actual, normalized)
    normalized.update(ACTOR64_CONFIGURATION_ORIGINALS)
    assert (
        hashlib.sha256(
            json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        == ACTOR64_RUNTIME_PINS_SHA256
    )


@pytest.mark.parametrize(
    "name,function",
    [
        ("context_tokens.py", "actor_budget_profile"),
        ("actor_release.py", "verify_actor_release"),
    ],
)
def test_only_original_configuration_guard_changed_in_fixed_installation(
    name: str, function: str
) -> None:
    installation = ReleaseInstallation.model_validate_json(
        json.dumps(json.loads(ORIGINAL.read_text())["installation"])
    )
    code = next(
        a for a in installation.manifest.artifacts if a.artifact_id == "installed-code"
    )
    relative = "src/lab_generate_skill/adapters/models/" + name
    original = (
        Path(code.root) / "lab_generate_skill/adapters/models" / name
    ).read_bytes()
    assert (
        hashlib.sha256(original).hexdigest()
        == ACTOR64_CONFIGURATION_ORIGINALS[relative]
    )
    old, new = ast.parse(original), ast.parse((ROOT / relative).read_bytes())
    old_fn = next(
        n for n in old.body if isinstance(n, ast.FunctionDef) and n.name == function
    )
    new_fn = next(
        n for n in new.body if isinstance(n, ast.FunctionDef) and n.name == function
    )
    if function == "actor_budget_profile":
        # Original four model revalidations and returned profile are unchanged.
        assert [dump(n) for n in old_fn.body[:5]] == [dump(n) for n in new_fn.body[:5]]
        assert dump(old_fn.body[-1]) == dump(new_fn.body[-1])
        assert len(old_fn.body) == 10 and len(new_fn.body) == 8
        assert [
            n.value.func.id
            for n in new_fn.body[5:7]
            if isinstance(n, ast.Expr)
            and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Name)
        ] == ["check_actor_model_configuration", "check_actor_parameter_configuration"]
        new_fn.body = old_fn.body
    else:
        index = next(
            i
            for i, n in enumerate(new_fn.body)
            if isinstance(n, ast.Expr)
            and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Name)
            and n.value.func.id == "check_actor_model_configuration"
        )
        # One reference-schema check became the shared stricter byte/schema
        # check. All original reads, file checks, authorities and closes remain.
        assert len(new_fn.body) == len(old_fn.body)
        assert isinstance(old_fn.body[index], ast.If)
        new_fn.body[index] = old_fn.body[index]
    # Import changes supply only the extracted validators. The original rest
    # of each module, including worker/count and actual release I/O, is exact.
    old.body = [n for n in old.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
    new.body = [n for n in new.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
    assert dump(old) == dump(new)


def software_with_extraction() -> tuple[bytes, bytes]:
    validation, software = documents()
    current = json.loads(software)
    current["files"].update(ACTOR64_CONFIGURATION_EXTRACTION)
    return validation, json.dumps(current).encode()


def test_exact_extraction_uses_the_same_actor64_configuration_and_parameters() -> None:
    validation, original = documents()
    _, current = software_with_extraction()
    assert select(validation, current) == select(validation, original)


@pytest.mark.parametrize(
    "name",
    [
        *ACTOR64_RUNTIME_FILES,
        "src/lab_generate_skill/domain/actor_configuration.py",
    ],
)
@pytest.mark.parametrize("fault", ["changed", "missing"])
def test_any_runtime_or_extracted_dependency_drift_is_refused(
    name: str, fault: str
) -> None:
    validation, current = software_with_extraction()
    value = json.loads(current)
    if fault == "changed":
        value["files"][name] = "f" * 64
    else:
        value["files"].pop(name)
    with pytest.raises(EvidenceIntegrityError):
        select(validation, json.dumps(value).encode())
