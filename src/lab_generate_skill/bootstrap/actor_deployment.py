"""Accepted Actor64 defaults with explicit proven hardware configuration.

This freezes one proven deployment, not a tier scheduler or execution permit.
The original resource/source authorities and full request hard gates still apply.
"""

import hashlib
import json
from typing import Any
from lab_generate_skill.domain.actor_engine import (
    ActorEngineConfig,
    LocalActorParameters,
)
from lab_generate_skill.domain.actor_context_count import digest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.adapters.processes.wire_json import json_object
from lab_generate_skill.policies.actor_prepared_qualification import (
    qualified_prepared_runtime_pins,
)

ACTOR64_VALIDATION_PATH = (
    "experiments/framework-actor-long-context-20261101-v1/acceptance.json"
)
ACTOR64_VALIDATION_SHA256 = (
    "95e8a0826862d7f1d692108b26eac722e699f8ee95d8d1f381e6d3aab11b9be4"
)
# Only actual closed resource receipts are selectable. No task/source grant.
ACTOR64_A10040_VALIDATION_PATH = (
    "experiments/framework-actor-long-context-20261101-v1/native64-4907925/result.json"
)
ACTOR64_A10040_VALIDATION_SHA256 = (
    "5d19ef723c1c262b3372635001754fac7a6ff3c97f0090f86d7487b8474df20f"
)
ACTOR64_NATIVE_RESOURCE_SCHEMA = "actor-native64-resource-result/1"
ACTOR64_RESOURCE_CLASSES = {ACTOR64_A10040_VALIDATION_SHA256: "a100_40gb"}
ACTOR64_RESOURCE_VALIDATIONS = {"a100_40gb": ACTOR64_A10040_VALIDATION_PATH}
ACTOR64_ENGINE_SHA256 = (
    "3235ed9175cc248c02d2422bec02ecf07d6e6cf7c63951d96f97cfed558dad5f"
)
ACTOR64_INVENTORY_SHA256 = (
    "3580a3d3854f18cf4b2ce7548afb899d82d055872076b0e2f1c031c9d8923f22"
)
ACTOR64_RUNTIME_PINS_SHA256 = (
    "e0ebbe70e83442ce8a533086d37c16cdcf68e603dabaf624628653f75456a80f"
)
ACTOR64_RUNTIME_FILES = (
    "src/lab_generate_skill/domain/actor_engine.py",
    "src/lab_generate_skill/domain/actor_long_context.py",
    "src/lab_generate_skill/adapters/models/actor_long_context.py",
    "src/lab_generate_skill/adapters/models/causal_session.py",
    "src/lab_generate_skill/adapters/models/causal_transformers.py",
    "src/lab_generate_skill/adapters/models/transformers_actor.py",
    "src/lab_generate_skill/adapters/models/transformers_actor_session.py",
    "src/lab_generate_skill/adapters/models/resident_state.py",
    "src/lab_generate_skill/adapters/models/actor_service.py",
    "src/lab_generate_skill/adapters/models/actor_worker_protocol.py",
    "src/lab_generate_skill/adapters/models/actor_count_protocol.py",
    "src/lab_generate_skill/adapters/models/actor_worker_client.py",
    "src/lab_generate_skill/adapters/models/context_tokens.py",
    "src/lab_generate_skill/adapters/models/context_count_review.py",
    "src/lab_generate_skill/adapters/models/actor_release.py",
    "tests/framework/generator_model_assets.py",
)

# Exact configuration-only extraction. Original inference/resource pins below
# remain required; neither arbitrary edited runtime nor a new model is admitted.
# Software: Admin package4902262 original114 behavior +4902273 type/combination.
# The configuration-extraction compatibility test compares the original
# immutable installation and every unchanged runtime pin before release use.
ACTOR64_CONFIGURATION_EXTRACTION = {
    "src/lab_generate_skill/adapters/models/context_tokens.py": "bf752f44c136e16f6a4e705073b2dfe4785cc14ebe1889cc6ca932822739a479",
    "src/lab_generate_skill/adapters/models/actor_release.py": "a11992b6506b5a95418b3469865691859a505a85bf3e085b5c55ec4d463579bb",
    "src/lab_generate_skill/domain/actor_configuration.py": "88387a217b751c61d4707c51643a39b6253511a7404a8ccef2ca81ddab5bb4cf",
}
ACTOR64_CONFIGURATION_ORIGINALS = {
    "src/lab_generate_skill/adapters/models/context_tokens.py": "25b1e45f7296576bc2409c7f54bc376ca5c572d9d6524dc62bfed64d13b52068",
    "src/lab_generate_skill/adapters/models/actor_release.py": "124e226b4e36905d4ea23b79785f28f5d3132038d5116036444427a6be16d04f",
}


def _document(
    reference: EvidenceRef, raw: bytes, schema: str, maximum: int
) -> dict[str, Any]:
    reference = EvidenceRef.model_validate(reference)
    if (
        (reference.visibility, reference.content_schema, reference.media_type)
        != ("private", schema, "application/json")
        or type(raw) is not bytes
        or not 0 < len(raw) <= maximum
        or (len(raw), hashlib.sha256(raw).hexdigest())
        != (reference.size_bytes, reference.sha256)
    ):
        raise EvidenceIntegrityError(
            "Complete original Actor deployment evidence required"
        )
    return json_object(raw)


def _qualified_native_configuration(
    config: ActorEngineConfig,
    inventory: str,
    resource_ref: EvidenceRef,
    resource: bytes,
) -> ActorEngineConfig:
    resource_ref = EvidenceRef.model_validate(resource_ref)
    target = ACTOR64_RESOURCE_CLASSES.get(resource_ref.sha256)
    measured = _document(resource_ref, resource, ACTOR64_NATIVE_RESOURCE_SCHEMA, 65536)
    if (
        target is None
        or measured.get("passed") is not True
        or measured.get("qualification_gpu_class") != target
        or measured.get("model_inventory_sha256") != inventory
        or measured.get("engine_closed") is not True
        or measured.get("staged_root_removed") is not True
        or measured.get("allocated_after_close_bytes") != 0
        or measured.get("reserved_after_close_bytes") != 0
        or measured.get("cleanup_errors") != []
        or measured.get("website_actions") != 0
        or measured.get("paid_calls") != 0
        or config.long_context is None
    ):
        raise EvidenceIntegrityError(
            "Exact closed Actor64 hardware resource qualification required"
        )
    values = config.model_dump(mode="json")
    values["long_context"] = {
        **config.long_context.model_dump(mode="json"),
        "gpu_class": target,
    }
    selected = ActorEngineConfig.model_validate_json(json.dumps(values))
    natural, pressure = measured.get("natural_eos"), measured.get(
        "full_window_pressure"
    )
    if (
        measured.get("engine_config") != selected.model_dump(mode="json")
        or not isinstance(natural, dict)
        or not isinstance(pressure, dict)
        or natural.get("input_tokens") != 61440
        or natural.get("finish_reason") != "stop"
        or pressure.get("input_tokens") != 61440
        or pressure.get("output_tokens") != 4096
        or pressure.get("finish_reason") != "length"
        or natural.get("all_logits_to_keep_one") is not True
        or pressure.get("all_logits_to_keep_one") is not True
        or pressure.get("first_forward") != {"input_tokens": 61440, "logits_to_keep": 1}
    ):
        raise EvidenceIntegrityError(
            "Qualified complete Actor64 resource envelope changed"
        )
    return selected


def accepted_actor_defaults(
    original: ActorEngineConfig,
    model_inventory_sha256: str,
    validation_ref: EvidenceRef,
    validation: bytes,
    software_ref: EvidenceRef,
    software: bytes,
    *,
    resource_ref: EvidenceRef | None = None,
    resource: bytes | None = None,
) -> tuple[ActorEngineConfig, LocalActorParameters]:
    """No I/O or dispatch; reject changed proof/runtime instead of silently falling back."""
    original = ActorEngineConfig.model_validate(original)
    if (resource_ref is None) != (resource is None):
        raise EvidenceIntegrityError(
            "Complete explicit resource reference and bytes required"
        )
    if resource_ref is not None:
        resource_ref = EvidenceRef.model_validate(resource_ref)
    validation_ref = EvidenceRef.model_validate(validation_ref)
    software_ref = EvidenceRef.model_validate(software_ref)
    accepted = _document(
        validation_ref, validation, "actor-long-reconciled-acceptance/1", 65536
    )
    if (
        validation_ref.sha256 != ACTOR64_VALIDATION_SHA256
        or accepted.get("schema_version") != "actor-long-reconciled-acceptance/1"
        or accepted.get("passed") is not True
        or accepted.get("long_inference_methods_exact") is not True
        or model_inventory_sha256 != ACTOR64_INVENTORY_SHA256
    ):
        raise EvidenceIntegrityError(
            "Original accepted A40 resource/model qualification required"
        )
    current = _document(software_ref, software, "framework-check/3", 16 * 1024**2)
    if (
        current.get("schema_version") != "framework-check/3"
        or current.get("passed") is not True
        or current.get("source_stable_during_checks") is not True
    ):
        raise EvidenceIntegrityError(
            "Accepted stable current Actor software gate required"
        )
    files = current.get("files")
    if type(files) is not dict or any(
        type(files.get(name)) is not str for name in ACTOR64_RUNTIME_FILES
    ):
        raise EvidenceIntegrityError(
            "Actor default software omits qualified runtime pins"
        )
    pins = {name: files[name] for name in ACTOR64_RUNTIME_FILES}
    pins = qualified_prepared_runtime_pins(files, pins)
    if all(
        files.get(name) == value
        for name, value in ACTOR64_CONFIGURATION_EXTRACTION.items()
    ):
        # Only this complete, checked extraction may substitute these two
        # configuration validators. All remaining original runtime bytes must
        # still produce the original qualification digest. No fallback tier.
        pins.update(ACTOR64_CONFIGURATION_ORIGINALS)
    if (
        hashlib.sha256(
            json.dumps(pins, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        != ACTOR64_RUNTIME_PINS_SHA256
    ):
        raise EvidenceIntegrityError(
            "Actor runtime changed since accepted resource qualification"
        )
    config = original
    if original.schema_version == "actor-engine-config/1":
        config = ActorEngineConfig.model_validate(
            {
                **original.model_dump(),
                "schema_version": "actor-engine-config/2",
                "context_window": 65536,
                "long_context": {"gpu_class": "a40"},
            }
        )
    if (
        resource_ref is not None
        and config.long_context is not None
        and config.long_context.gpu_class
        == ACTOR64_RESOURCE_CLASSES.get(resource_ref.sha256)
    ):
        values = config.model_dump(mode="json")
        values["long_context"] = {
            **config.long_context.model_dump(mode="json"),
            "gpu_class": "a40",
        }
        config = ActorEngineConfig.model_validate_json(json.dumps(values))
    if digest(config) != ACTOR64_ENGINE_SHA256:
        raise EvidenceIntegrityError(
            "Actor default configuration differs from qualified A40 deployment"
        )
    if resource_ref is not None and resource is not None:
        config = _qualified_native_configuration(
            config, model_inventory_sha256, resource_ref, resource
        )
    return config, LocalActorParameters(
        max_input_tokens=61440,
        max_new_tokens=4096,
        seed=42,
        temperature=0.7,
        top_p=0.95,
        enable_thinking=False,
    )
