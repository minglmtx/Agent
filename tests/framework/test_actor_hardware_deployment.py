"""Use exact actual resource7925, with no model/site/resource acquisition."""

import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.actor_deployment import (
    accepted_actor_defaults,
    ACTOR64_INVENTORY_SHA256,
    ACTOR64_A10040_VALIDATION_PATH,
    ACTOR64_NATIVE_RESOURCE_SCHEMA,
)
from lab_generate_skill.domain.actor_engine import (
    ActorEngineConfig,
    LocalActorParameters,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from actor_engine_fixtures import config
from test_actor_deployment_defaults import documents, reference

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")


def select(
    raw: Any,
    ref: EvidenceRef | None,
    *,
    original: ActorEngineConfig | None = None,
    software_value: bytes | None = None,
) -> tuple[ActorEngineConfig, LocalActorParameters]:
    validation, software = documents()
    if software_value is not None:
        software = software_value
    return accepted_actor_defaults(
        config() if original is None else original,
        ACTOR64_INVENTORY_SHA256,
        reference(validation, "actor-long-reconciled-acceptance/1"),
        validation,
        reference(software, "framework-check/3"),
        software,
        resource_ref=ref,
        resource=raw,
    )


def test_actual_a10040_changes_only_hardware_keeps_budget_and_is_repeatable() -> None:
    raw = (W / ACTOR64_A10040_VALIDATION_PATH).read_bytes()
    ref = reference(raw, ACTOR64_NATIVE_RESOURCE_SCHEMA)
    baseline, params = select(None, None)
    selected, actual = select(raw, ref)
    assert selected.long_context is not None
    assert selected.long_context.gpu_class == "a100_40gb"
    values = selected.model_dump(mode="json")
    values["long_context"]["gpu_class"] = "a40"
    assert ActorEngineConfig.model_validate_json(json.dumps(values)) == baseline
    assert actual == params
    assert (actual.max_input_tokens, actual.max_new_tokens, actual.temperature) == (
        61440,
        4096,
        0.7,
    )
    assert select(raw, ref, original=selected) == (selected, actual)
    assert select(raw, ref) == (selected, actual)


@pytest.mark.parametrize(
    "fault",
    [
        "empty",
        "wrong_type",
        "changed_bytes",
        "changed_record",
        "foreign_schema",
        "public",
        "partial_ref",
        "partial_bytes",
        "foreign_card",
        "foreign_runtime",
        "missing_current_runtime",
        "changed_current_runtime",
    ],
)
def test_foreign_or_partial_hardware_proof_never_grants_configuration(
    fault: str,
) -> None:
    raw: Any = (W / ACTOR64_A10040_VALIDATION_PATH).read_bytes()
    ref: EvidenceRef | None = reference(raw, ACTOR64_NATIVE_RESOURCE_SCHEMA)
    baseline, _ = select(None, None)
    original = baseline
    software_value = None
    if fault == "empty":
        raw = b""
    elif fault == "wrong_type":
        raw = "wrong"
    elif fault == "changed_bytes":
        raw += b" "
    elif fault == "changed_record":
        value = json.loads(raw)
        value["passed"] = False
        raw = json.dumps(value).encode()
        ref = reference(raw, ACTOR64_NATIVE_RESOURCE_SCHEMA)
    elif fault == "foreign_schema":
        ref = reference(raw, "framework-check/3")
    elif fault == "public":
        ref = reference(raw, ACTOR64_NATIVE_RESOURCE_SCHEMA).model_copy(
            update={"visibility": "public"}
        )
    elif fault == "partial_ref":
        ref = None
    elif fault == "partial_bytes":
        raw = None
    elif fault in {"foreign_card", "foreign_runtime"}:
        values = baseline.model_dump(mode="json")
        if fault == "foreign_card":
            values["long_context"]["gpu_class"] = "a100_80gb"
        else:
            values["cpu_threads"] += 1
        original = ActorEngineConfig.model_validate_json(json.dumps(values))
    else:
        _, software = documents()
        data = json.loads(software)
        key = "src/lab_generate_skill/adapters/models/actor_long_context.py"
        if fault == "missing_current_runtime":
            del data["files"][key]
        else:
            data["files"][key] = "f" * 64
        software_value = json.dumps(data).encode()
    with pytest.raises((EvidenceIntegrityError, ValueError)):
        select(raw, ref, original=original, software_value=software_value)


@pytest.mark.parametrize("gpu_class", ["unknown", "a100_80gb", ""])
def test_unqualified_admin_install_choice_rejects_before_source_or_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, gpu_class: str
) -> None:
    import admin_production_installation as installation
    from lab_generate_skill.adapters.processes.deadline import DeadlineControl

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Unqualified choice reached source or model preparation")

    monkeypatch.setattr(installation, "verify_source", forbidden)
    with pytest.raises(ValueError, match="actually qualified"):
        installation.prepare_admin_installation(
            tmp_path / "installation",
            tmp_path / "absent-software.json",
            DeadlineControl(10, "unqualified-choice"),
            gpu_class=gpu_class,
        )
    assert not (tmp_path / "installation").exists()
