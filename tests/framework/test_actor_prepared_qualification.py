"""Exact old native envelope plus explicit prepared-worker compatibility, no GPU rerun."""

import ast
import copy
import hashlib
import json
from pathlib import Path
import pytest
from lab_generate_skill.bootstrap.actor_deployment import (
    ACTOR64_CONFIGURATION_EXTRACTION,
    ACTOR64_RUNTIME_FILES,
    ACTOR64_A10040_VALIDATION_PATH,
    ACTOR64_NATIVE_RESOURCE_SCHEMA,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from lab_generate_skill.policies.actor_prepared_qualification import (
    PREPARED_ACTOR_RUNTIME,
    PREPARED_ACTOR_ORIGINALS,
)
from lab_generate_skill.policies.actor_verified_context_qualification import (
    VERIFIED_ACTOR_RUNTIME,
)
from test_actor_configuration_compatibility import ORIGINAL, ROOT, WORKSPACE, dump
from test_actor_deployment_defaults import documents, select, reference
from test_actor_hardware_deployment import select as select_hardware


def selected_software() -> tuple[bytes, bytes]:
    validation, software = documents()
    value = json.loads(software)
    value["files"].update(ACTOR64_CONFIGURATION_EXTRACTION)
    value["files"].update(VERIFIED_ACTOR_RUNTIME)
    return validation, json.dumps(value).encode()


def test_exact_prepared_runtime_has_accepted_behavior_and_original_native_bodies() -> (
    None
):
    package = WORKSPACE / "experiments/framework-combined-release-20261030-v1"
    checked = package / "actor-prepared-window-checked-check-4948618"
    receipt = json.loads((checked / "result.json").read_bytes())
    scope = json.loads((checked / "scoped-acceptance.json").read_bytes())
    assert receipt["passed"] and receipt["source_stable_during_checks"]
    assert scope["passed"] and scope["unique_nodes"] == 320
    assert (
        scope["current_result_sha256"]
        == hashlib.sha256((checked / "result.json").read_bytes()).hexdigest()
    )
    for name, expected in PREPARED_ACTOR_RUNTIME.items():
        assert receipt["files"][name] == expected
        old_root = (
            WORKSPACE
            / "code/lab-generate-skill-actor-prepared-qualified-candidate-20261107"
        )
        assert hashlib.sha256((old_root / name).read_bytes()).hexdigest() == expected
    assert VERIFIED_ACTOR_RUNTIME and set(PREPARED_ACTOR_RUNTIME) <= set(
        VERIFIED_ACTOR_RUNTIME
    )
    for name, expected in VERIFIED_ACTOR_RUNTIME.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    required = {
        "test_actor_generation_windows",
        "test_actor_prepared_generation",
        "test_task_actor_generation_windows",
        "test_actor_engine",
        "test_actor_worker_process",
    }
    assert required <= {Path(row["node"].split("::")[0]).stem for row in scope["cases"]}
    installation = ReleaseInstallation.model_validate_json(
        json.dumps(json.loads(ORIGINAL.read_bytes())["installation"])
    )
    code = next(
        a for a in installation.manifest.artifacts if a.artifact_id == "installed-code"
    )
    for name, expected in PREPARED_ACTOR_ORIGINALS.items():
        raw = (Path(code.root) / name.removeprefix("src/")).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == expected
    name = "src/lab_generate_skill/adapters/models/transformers_actor.py"
    before = ast.parse((Path(code.root) / name.removeprefix("src/")).read_bytes())
    after = ast.parse((ROOT / name).read_bytes())

    def methods(tree: ast.Module) -> dict[str, ast.FunctionDef]:
        cls = next(
            n
            for n in tree.body
            if isinstance(n, ast.ClassDef) and n.name == "ResidentActorEngine"
        )
        return {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}

    old, new = methods(before), methods(after)
    for method in ("_raw_tokens", "_tokens", "config"):
        assert dump(old[method]) == dump(new[method])
    old_generation = next(n for n in old["generate"].body if isinstance(n, ast.With))
    assert dump(ast.Module(body=old_generation.body[1:], type_ignores=[])) == dump(
        ast.Module(body=new["_infer"].body, type_ignores=[])
    )
    # Reconstruct legacy generate by removing only the handoff invalidation
    # and inlining the exact extracted inference body. No native step changes.
    actual = copy.deepcopy(new["generate"])
    held = next(n for n in actual.body if isinstance(n, ast.With))
    assert dump(held.body[0]) == dump(ast.parse("self._prepared = None").body[0])
    assert dump(held.body[-1]) == dump(
        ast.parse("return self._infer(tokens, parameters, control)").body[0]
    )
    held.body = [*held.body[1:-1], *copy.deepcopy(new["_infer"].body)]
    assert dump(actual) == dump(old["generate"])
    assert dump(ast.Module(body=new["_close"].body, type_ignores=[])) == dump(
        ast.parse("self._prepared = None\nsuper()._close()")
    )


@pytest.mark.parametrize("gpu", ["a40", "a100_40gb"])
def test_original_hardware_envelope_consumes_complete_prepared_runtime(
    gpu: str,
) -> None:
    validation, software = selected_software()
    if gpu == "a40":
        actual = select(validation, software)
        old_validation, old_software = documents()
        assert actual == select(old_validation, old_software)
    else:
        raw = (WORKSPACE / ACTOR64_A10040_VALIDATION_PATH).read_bytes()
        ref = reference(raw, ACTOR64_NATIVE_RESOURCE_SCHEMA)
        actual = select_hardware(raw, ref, software_value=software)
        assert actual == select_hardware(raw, ref)
    cfg, params = actual
    assert cfg.long_context is not None
    assert cfg.context_window == 65536 and cfg.long_context.gpu_class == gpu
    assert (params.max_input_tokens, params.max_new_tokens) == (61440, 4096)


@pytest.mark.parametrize(
    "name",
    sorted(
        set(VERIFIED_ACTOR_RUNTIME)
        | set(ACTOR64_RUNTIME_FILES)
        | set(ACTOR64_CONFIGURATION_EXTRACTION)
    ),
)
@pytest.mark.parametrize("fault", ["changed", "missing"])
def test_partial_prepared_or_native_dependency_drift_never_reuses_qualification(
    name: str, fault: str
) -> None:
    validation, software = selected_software()
    value = json.loads(software)
    if fault == "changed":
        value["files"][name] = "f" * 64
    else:
        del value["files"][name]
    with pytest.raises(EvidenceIntegrityError):
        select(validation, json.dumps(value).encode())


@pytest.mark.parametrize("name", sorted(PREPARED_ACTOR_ORIGINALS))
def test_isolated_wrapper_patch_without_complete_window_path_is_rejected(
    name: str,
) -> None:
    validation, software = documents()
    value = json.loads(software)
    value["files"][name] = PREPARED_ACTOR_RUNTIME[name]
    with pytest.raises(EvidenceIntegrityError):
        select(validation, json.dumps(value).encode())
