"""Coherent category/model declarations; synthetic code/model roles, no inference.

Original source caller and allocation metadata use this Slurm job. The native,
browser, model assets and unrelated installed roles remain explicit unit facts.
Nothing here qualifies a production installation or actual hardware inference.
"""

from datetime import timedelta
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.bootstrap.shopping_category_actor_configuration import (
    category_actor_metadata,
)
from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
from lab_generate_skill.domain.actor_resource import ActorResourceSpec
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from lab_generate_skill.domain.release import ReleaseManifest
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from actor_resource_fixtures import resource_case
from actor_long_fixtures import long_config
from shopping_category_source_fixtures import source_unit_case
from storage_installation_fixtures import storage_installation

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
SOFTWARE = (
    W
    / "experiments/framework-combined-release-20261030-v1/adaptive-policy-check-4960593/result.json"
)


def run_input_case(
    root: Path, node: Path, patch: pytest.MonkeyPatch, original: Any
) -> Any:
    actor = resource_case(
        root / "actor", Path(sys.executable), engine_config=long_config()
    )
    manifest = ReleaseManifest.model_validate_json(
        actor.evidence.read(actor.spec.release_ref)
    )
    code = manifest.artifacts[0]
    files = {f.path: f for f in code.files}
    files.update(
        {f.path: f for f in storage_installation().manifest.artifacts[0].files}
    )
    manifest = ReleaseManifest.model_validate(
        manifest.model_copy(
            update={
                "artifacts": (
                    code.model_copy(
                        update={"files": tuple(files[k] for k in sorted(files))}
                    ),
                    *manifest.artifacts[1:],
                )
            }
        )
    )
    manifest_raw = manifest.model_dump_json().encode()
    release_ref = evidence_reference(
        manifest_raw, category_actor_metadata(manifest.schema_version)
    )
    binding = ActorModelBinding.model_validate_json(
        actor.evidence.read(actor.spec.model_binding_ref)
    )
    binding = binding.model_copy(update={"release_ref": release_ref})
    model_ref = evidence_reference(
        binding.model_dump_json().encode(), category_actor_metadata("model-binding/1")
    )
    installation = ReleaseInstallation(
        manifest=manifest,
        manifest_ref=release_ref,
        workspace_root=str(root),
        python_executable=str(sys.executable),
    )
    source_root = root / "source"
    source_root.mkdir()
    source = source_unit_case(
        source_root, node, patch, original, "none", installation=installation
    )
    store = source.site.evidence

    def retained(raw: bytes, ref: Any) -> None:
        metadata = EvidenceMetadata.model_validate(
            ref.model_dump(
                include={"media_type", "content_schema", "visibility", "producer"}
            )
        )
        assert store.put(raw, metadata) == ref

    retained(manifest_raw, release_ref)
    retained(binding.model_dump_json().encode(), model_ref)
    retained(actor.evidence.read(binding.engine_config_ref), binding.engine_config_ref)
    recovery = RecoveryPlan.model_validate_json(
        actor.evidence.read(actor.spec.token.recovery_ref)
    ).model_copy(update={"owner": source.owner.scope.owner})
    recovery_ref = store.put(
        recovery.model_dump_json().encode(),
        category_actor_metadata(recovery.schema_version),
    )
    spec = ActorResourceSpec.model_validate(
        actor.spec.model_copy(
            update={
                "release_ref": release_ref,
                "model_binding_ref": model_ref,
                "token": actor.spec.token.model_copy(
                    update={
                        "owner": source.owner.scope.owner,
                        "recovery_ref": recovery_ref,
                    }
                ),
            }
        )
    )
    published = source.run()
    scope = source.owner.scope.model_copy(
        update={
            "attempt_id": "category-candidate",
            "context_id": "category-candidate-context",
        }
    )
    operation = source.site.op.model_copy(
        update={
            "operation_id": "category-run-inputs",
            "attempt_id": None,
            "allocation_id": None,
            "recovery_ref": None,
            "deadline": source.site.clock.utcnow() + timedelta(seconds=300),
        }
    )
    parameters = LocalActorParameters(
        max_input_tokens=61440,
        max_new_tokens=4096,
        seed=42,
        temperature=0.7,
        top_p=0.95,
    )
    software = SOFTWARE.read_bytes()
    document = json.loads(software)
    from lab_generate_skill.bootstrap.actor_context_policy import (
        ACTOR_CONTEXT_IMPLEMENTATION_FILES,
        ACTOR_ADAPTIVE_IMPLEMENTATION_FILES,
    )

    project = Path(__file__).resolve().parents[2]
    for name in (
        *ACTOR_CONTEXT_IMPLEMENTATION_FILES,
        *ACTOR_ADAPTIVE_IMPLEMENTATION_FILES,
    ):
        assert (
            document["files"][name]
            == hashlib.sha256((project / name).read_bytes()).hexdigest()
        )
    software_ref = evidence_reference(
        software, category_actor_metadata("framework-check/3")
    )
    retained(software, software_ref)
    return SimpleNamespace(
        source=source,
        published=published,
        scope=scope,
        actor=spec,
        binding=binding,
        parameters=parameters,
        software_ref=software_ref,
        software=software,
        operation=operation,
        store=store,
        controls=source.site.controls,
    )
