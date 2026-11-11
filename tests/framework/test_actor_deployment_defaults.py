"""Known A40 default consumes exact proof/pins; no source or model requests."""

import hashlib
import json
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.bootstrap.actor_deployment import (
    accepted_actor_defaults,
    ACTOR64_ENGINE_SHA256,
    ACTOR64_INVENTORY_SHA256,
    ACTOR64_VALIDATION_SHA256,
)
from lab_generate_skill.domain.actor_context_count import digest
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from actor_engine_fixtures import config
from actor_long_fixtures import long_config
from source_actor_context_fixtures import source_context_case

FIXTURES = Path(__file__).parent / "fixtures/actor64-default"


def reference(raw: bytes, schema: str) -> EvidenceRef:
    return evidence_reference(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema=schema,
            visibility="private",
            producer="unit-actor-deployment",
        ),
    )


def documents() -> tuple[bytes, bytes]:
    validation = (FIXTURES / "resource-validation.json").read_bytes()
    software = json.dumps(
        {
            "schema_version": "framework-check/3",
            "passed": True,
            "source_stable_during_checks": True,
            "files": json.loads((FIXTURES / "runtime-pins.json").read_text()),
        }
    ).encode()
    return validation, software


def select(
    validation: bytes,
    software: bytes,
    *,
    inventory: Any = ACTOR64_INVENTORY_SHA256,
    original: Any = None,
) -> Any:
    return accepted_actor_defaults(
        config() if original is None else original,
        inventory,
        reference(validation, "actor-long-reconciled-acceptance/1"),
        validation,
        reference(software, "framework-check/3"),
        software,
    )


def test_a40_default_keeps_exact_config_output_and_existing_source_ABC_parameters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validation, software = documents()
    assert hashlib.sha256(validation).hexdigest() == ACTOR64_VALIDATION_SHA256
    original = config()
    raw = original.model_dump_json()
    cfg, parameters = select(validation, software, original=original)
    assert cfg == long_config() and digest(cfg) == ACTOR64_ENGINE_SHA256
    assert parameters.max_new_tokens == 4096 and parameters.max_input_tokens == 61440
    assert parameters.temperature == 0.7 and parameters.top_p == 0.95
    assert parameters.seed == 42 and not parameters.enable_thinking
    assert original.model_dump_json() == raw
    assert select(validation, software, original=cfg) == (cfg, parameters)
    # Exact DTO equivalence with the already checked long source/authority/closed
    # review fixture; no second Actor/browser execution is needed for this check.
    c = source_context_case(tmp_path / "case", monkeypatch, engine_config=cfg)
    assert c.actor.spec.engine_config == cfg and c.params == parameters
    c.client.close(c.actor.controls.bind(c.actor.op))
    assert c.loader.loads == c.loader.session.calls == c.session.calls == 0


@pytest.mark.parametrize(
    "fault", ["bytes", "replace-record", "public", "schema", "truncated"]
)
def test_a40_default_rejects_changed_or_foreign_resource_proof(fault: str) -> None:
    validation, software = documents()
    ref = reference(validation, "actor-long-reconciled-acceptance/1")
    if fault == "bytes":
        validation += b" "
    elif fault == "replace-record":
        validation = validation.replace(b'"passed": true', b'"passed": false', 1)
        ref = reference(validation, ref.content_schema)
    elif fault == "public":
        ref = ref.model_copy(update={"visibility": "public"})
    elif fault == "schema":
        ref = ref.model_copy(update={"content_schema": "framework-check/3"})
    else:
        validation = validation[:100]
        ref = reference(validation, ref.content_schema)
    with pytest.raises((EvidenceIntegrityError, ValueError)):
        accepted_actor_defaults(
            config(),
            ACTOR64_INVENTORY_SHA256,
            ref,
            validation,
            reference(software, "framework-check/3"),
            software,
        )


@pytest.mark.parametrize(
    "fault",
    [
        "failed",
        "unstable",
        "missing",
        "model-code",
        "weight-reader",
        "schema",
        "wrong-role",
    ],
)
def test_a40_default_rejects_unqualified_current_software_without_standard_fallback(
    fault: str,
) -> None:
    validation, software = documents()
    data = json.loads(software)
    if fault == "failed":
        data["passed"] = False
    elif fault == "unstable":
        data["source_stable_during_checks"] = False
    elif fault == "missing":
        data["files"].pop(next(iter(data["files"])))
    elif fault in ["model-code", "weight-reader"]:
        name = (
            "tests/framework/generator_model_assets.py"
            if fault == "weight-reader"
            else "src/lab_generate_skill/adapters/models/causal_transformers.py"
        )
        data["files"][name] = "f" * 64
    elif fault == "schema":
        data["schema_version"] = "framework-check/2"
    else:
        data["role"] = "teacher"
        data["files"] = {}
    with pytest.raises(EvidenceIntegrityError):
        select(validation, json.dumps(data).encode())


@pytest.mark.parametrize(
    "field,value",
    [
        ("cpu_threads", 1),
        ("dtype", "float16"),
        ("context_window", 131072),
        ("gpu", "a100_80gb"),
        ("packages", None),
    ],
)
def test_a40_default_does_not_borrow_other_runtime_or_card_qualification(
    field: str, value: Any
) -> None:
    validation, software = documents()
    cfg = long_config()
    if field == "gpu":
        assert cfg.long_context is not None
        cfg = cfg.model_copy(
            update={
                "long_context": cfg.long_context.model_copy(update={"gpu_class": value})
            }
        )
    else:
        cfg = cfg.model_copy(update={field: value})
    with pytest.raises((EvidenceIntegrityError, ValidationError)):
        select(validation, software, original=cfg)


@pytest.mark.parametrize("inventory", [None, "", True, 0, "0" * 64])
def test_a40_default_requires_original_model_inventory(inventory: Any) -> None:
    validation, software = documents()
    with pytest.raises(EvidenceIntegrityError):
        select(validation, software, inventory=inventory)


@pytest.mark.parametrize("raw", [None, "", b"", {}, [], b"null"])
def test_a40_default_empty_and_wrong_type_proof_has_no_configuration(raw: Any) -> None:
    validation, software = documents()
    with pytest.raises((EvidenceIntegrityError, ValidationError, ValueError)):
        accepted_actor_defaults(
            config(),
            ACTOR64_INVENTORY_SHA256,
            reference(validation, "actor-long-reconciled-acceptance/1"),
            raw,
            reference(software, "framework-check/3"),
            software,
        )
