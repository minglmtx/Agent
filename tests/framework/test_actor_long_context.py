"""Actor-only version/resource/loader contract; new profiles remain unpublished."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
import json
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.actor_engine import ActorEngineConfig
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    ActorInputBudgetExceeded,
    OwnershipConflict,
)
from lab_generate_skill.adapters.models.actor_long_context import (
    actor_position_override,
)
from lab_generate_skill.adapters.models.transformers_actor_session import (
    TransformersActorSession,
)
from lab_generate_skill.adapters.models.transformers_actor import ResidentActorEngine
from lab_generate_skill.adapters.models.context_tokens import actor_budget_profile
from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from actor_long_fixtures import long_config, cuda_runtime, loader_modules
from actor_engine_fixtures import config, setup


def test_old_actor_engine_canonical_bytes_stay_exact_and_v2_is_explicit() -> None:
    old = config()
    raw = old.model_dump_json()
    assert "long_context" not in raw
    assert json.loads(raw) == {
        "schema_version": "actor-engine-config/1",
        "model_type": "qwen2",
        "dtype": "bfloat16",
        "device": "cuda:0",
        "cpu_threads": 2,
        "context_window": 200,
        "packages": [p.model_dump() for p in old.packages],
    }
    assert ActorEngineConfig.model_validate_json(raw).model_dump_json() == raw
    for value in [None, {"gpu_class": "a40"}]:
        with pytest.raises(ValidationError):
            ActorEngineConfig.model_validate(
                {**old.model_dump(), "long_context": value}
            )
    new = long_config()
    assert ActorEngineConfig.model_validate_json(new.model_dump_json()) == new
    assert new.schema_version == "actor-engine-config/2" and new.context_window == 65536


@pytest.mark.parametrize(
    "field,value",
    [
        ("context_window", 98304),
        ("context_window", True),
        ("context_window", 32768),
        ("dtype", "float32"),
        ("long_context", None),
        ("schema_version", "generator-engine-config/2"),
        ("long_context", {}),
        ("long_context", {"gpu_class": "a100_mig"}),
        ("long_context", {"gpu_class": "a40", "factor": 2.0}),
        (
            "long_context",
            {"gpu_class": "a40", "original_max_position_embeddings": 131072},
        ),
        ("long_context", {"gpu_class": "a40", "attention_backend": "eager"}),
    ],
)
def test_long_actor_config_rejects_unsupported_implicit_or_cross_role_inputs(
    field: str, value: object
) -> None:
    raw = long_config().model_dump()
    raw[field] = value
    with pytest.raises(ValidationError):
        ActorEngineConfig.model_validate(raw)


@pytest.mark.parametrize("gpu", ["a40", "rtx_pro_6000_blackwell"])
def test_128k_is_not_enabled_by_large_non_a100_memory(gpu: str) -> None:
    with pytest.raises(ValidationError):
        long_config(131072, gpu)


@pytest.mark.parametrize(
    "target,name,memory,sms",
    [
        ("a40", "NVIDIA A40", 46, 84),
        ("a100_40gb", "NVIDIA A100-SXM4-40GB", 40, 108),
        ("a100_80gb", "NVIDIA A100-SXM4-80GB", 80, 108),
        (
            "rtx_pro_6000_blackwell",
            "NVIDIA RTX PRO 6000 Blackwell Server Edition",
            96,
            188,
        ),
    ],
)
def test_long_actor_checks_actual_card_class_not_partition(
    target: str, name: str, memory: int, sms: int
) -> None:
    window = 131072 if target.startswith("a100") else 65536
    position = actor_position_override(
        long_config(window, target), cuda_runtime(name, memory, sms)
    )
    assert position.rope_scaling == {
        "rope_type": "yarn",
        "factor": 4.0,
        "original_max_position_embeddings": 32768,
    }
    assert position.maximum_window == 131072 and position.attention_backend == "sdpa"


@pytest.mark.parametrize(
    "fault",
    [
        "name",
        "memory",
        "sms",
        "mig_name",
        "mig_uuid",
        "invisible",
        "many",
        "a100_variant",
        "rtx_cuda",
        "rtx_arch",
    ],
)
def test_bad_long_resource_facts_refuse_before_loading(fault: str) -> None:
    torch = cuda_runtime()
    cfg = long_config()
    p = torch.cuda.get_device_properties(0)
    if fault == "name":
        p.name = "NVIDIA RTX A6000"
    elif fault == "memory":
        p.total_memory = 20 * 1024**3
    elif fault == "sms":
        p.multi_processor_count = 42
    elif fault == "mig_name":
        p.name = "NVIDIA A100-SXM4-40GB MIG 1g.5gb"
    elif fault == "mig_uuid":
        p.uuid = "MIG-unit"
    elif fault == "invisible":
        torch.cuda.is_available = lambda: False
    elif fault == "many":
        torch.cuda.device_count = lambda: 2
    elif fault == "a100_variant":
        cfg = long_config(131072, "a100_80gb")
        torch = cuda_runtime("NVIDIA A100-SXM4-40GB", 40, 108)
    elif fault in ("rtx_cuda", "rtx_arch"):
        cfg = long_config(65536, "rtx_pro_6000_blackwell")
        torch = cuda_runtime("NVIDIA RTX PRO 6000 Blackwell Server Edition", 96, 188)
        if fault == "rtx_cuda":
            torch.version.cuda = "12.6"
        else:
            torch.cuda.get_arch_list = lambda: ["sm_90"]
    with pytest.raises(EvidenceIntegrityError):
        actor_position_override(cfg, torch)


def test_long_loader_uses_private_config_overlay_and_keeps_original_standard_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = loader_modules(monkeypatch)
    first = TransformersActorSession(tmp_path, long_config())
    assert (
        fake.original.rope_scaling is None
        and fake.original.max_position_embeddings == 32768
    )
    assert fake.calls["load_options"]["attn_implementation"] == "sdpa"
    assert first._model.config.max_position_embeddings == 131072
    assert first._config.context_window == 65536
    first.close()
    standard = config().model_copy(update={"context_window": 32768})
    second = TransformersActorSession(tmp_path, standard)
    assert (
        "config" not in fake.calls["load_options"]
        and "attn_implementation" not in fake.calls["load_options"]
    )
    assert second._model.config.rope_scaling is None and fake.calls["auto_configs"] == 1
    second.close()
    assert fake.calls["loads"] == fake.calls["closed"] == 2
    assert fake.calls["workspaces_cleared"] == 1


@pytest.mark.parametrize(
    "fault", ["existing_rope", "base_window", "loaded_backend", "load_failure"]
)
def test_long_loader_never_overlays_wrong_base_or_retries_partial_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    fake = loader_modules(monkeypatch)
    if fault == "existing_rope":
        fake.original.rope_scaling = {"rope_type": "other"}
    elif fault == "base_window":
        fake.original.max_position_embeddings = 16384
    else:
        load = fake.transformer.AutoModelForCausalLM.from_pretrained

        def failed(*args: Any, **kwargs: Any) -> Any:
            if fault == "load_failure":
                raise MemoryError("unit OOM before completion")
            value = load(*args, **kwargs)
            value.config._attn_implementation = "eager"
            return value

        fake.transformer.AutoModelForCausalLM.from_pretrained = failed
    with pytest.raises((EvidenceIntegrityError, MemoryError)):
        TransformersActorSession(tmp_path, long_config())
    assert fake.calls["closed"] == 1 and fake.calls["loads"] <= 1
    assert fake.calls["workspaces_cleared"] == 1


def test_long_close_repeatedly_releases_workspace_without_reloading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = loader_modules(monkeypatch)
    session = TransformersActorSession(tmp_path, long_config())
    for _ in range(2):
        session.close()
        assert session._model is None and session._tokenizer is None
    assert fake.calls["loads"] == 1
    assert fake.calls["closed"] == fake.calls["workspaces_cleared"] == 2


@pytest.mark.parametrize("fault", ["workspace", "allocator", "both", "cancelled"])
def test_long_close_keeps_release_errors_and_attempts_independent_allocator_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    fake = loader_modules(monkeypatch)
    session = TransformersActorSession(tmp_path, long_config())
    primary = (
        KeyboardInterrupt("unit cancelled close")
        if fault == "cancelled"
        else RuntimeError("unit workspace release failed")
    )
    secondary = MemoryError("unit allocator release failed")
    calls: list[str] = []

    def clear() -> None:
        calls.append("workspace")
        if fault != "allocator":
            raise primary

    def empty() -> None:
        calls.append("allocator")
        if fault in ("allocator", "both"):
            raise secondary

    fake.torch._C._cuda_clearCublasWorkspaces = clear
    fake.torch.cuda.empty_cache = empty
    with pytest.raises(BaseException) as caught:
        session.close()
    if fault == "both":
        assert isinstance(caught.value, BaseExceptionGroup)
        assert caught.value.exceptions == (primary, secondary)
    else:
        assert caught.value is (secondary if fault == "allocator" else primary)
    assert calls == ["workspace", "allocator"]
    assert session._model is None and session._tokenizer is None
    assert fake.calls["loads"] == 1


def test_long_partial_load_keeps_primary_and_all_close_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = loader_modules(monkeypatch)
    primary, workspace, allocator = (
        MemoryError("unit model OOM"),
        RuntimeError("unit workspace release failed"),
        OSError("unit allocator release failed"),
    )
    calls: list[str] = []

    def load(*args: Any, **kwargs: Any) -> Any:
        calls.append("load")
        raise primary

    def clear() -> None:
        calls.append("workspace")
        raise workspace

    def empty() -> None:
        calls.append("allocator")
        raise allocator

    fake.transformer.AutoModelForCausalLM.from_pretrained = load
    fake.torch._C._cuda_clearCublasWorkspaces = clear
    fake.torch.cuda.empty_cache = empty
    with pytest.raises(BaseExceptionGroup) as caught:
        TransformersActorSession(tmp_path, long_config())
    assert caught.value.exceptions[0] is primary
    cleanup = caught.value.exceptions[1]
    assert isinstance(cleanup, BaseExceptionGroup)
    assert cleanup.exceptions == (workspace, allocator)
    assert calls == ["load", "workspace", "allocator"]


def test_long_close_without_cuda_still_discards_partial_python_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = loader_modules(monkeypatch)
    session = TransformersActorSession(tmp_path, long_config())
    fake.torch.cuda.is_available = lambda: False
    session.close()
    assert session._model is None and session._tokenizer is None
    assert fake.calls["closed"] == fake.calls["workspaces_cleared"] == 0


@pytest.mark.parametrize("window", [65536, 131072])
@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_new_windows_keep_full_count_input_output_hard_boundaries(
    tmp_path: Path, window: int, offset: int
) -> None:
    old, loader, request, parameters, control = setup(tmp_path)
    cfg = long_config(window, "a100_80gb" if window == 131072 else "a40")
    engine = ResidentActorEngine(old.artifact, cfg, loader=loader)
    count = window - 4096 + offset
    loader.session.tokens = (3,) * count
    parameters = parameters.model_copy(
        update={"max_input_tokens": window - 4096, "max_new_tokens": 4096}
    )
    measured = engine.measure(request, parameters, control)
    assert measured.input_tokens == count and loader.session.calls == 0
    if offset > 0:
        with pytest.raises(ActorInputBudgetExceeded):
            engine.validate(request, parameters, control)
    else:
        engine.validate(request, parameters, control)
    assert loader.session.calls == 0
    engine.close(control)


def test_actual_long_constructor_rejects_card_before_any_model_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = loader_modules(monkeypatch)
    fake.torch.cuda.get_device_properties(0).uuid = "MIG-unit-ineligible"
    with pytest.raises(EvidenceIntegrityError, match="MIG"):
        TransformersActorSession(tmp_path, long_config())
    assert (
        fake.calls["loads"] == fake.calls["auto_configs"] == fake.calls["closed"] == 0
    )


@pytest.mark.parametrize("reserve", [1, 1536, 2048, 3481, 3482, 4095])
def test_long_output_reserve_cannot_be_squeezed_to_fit_or_rebased(
    tmp_path: Path, reserve: int
) -> None:
    original, loader, request, parameters, control = setup(tmp_path)
    cfg = long_config()
    assert cfg.long_context is not None
    assert cfg.long_context.baseline_output_reserve == 4096
    assert cfg.long_context.min_retained_fraction == 0.85
    assert cfg.long_context.minimum_output_reserve == 3482
    engine = ResidentActorEngine(original.artifact, cfg, loader=loader)
    parameters = parameters.model_copy(update={"max_new_tokens": reserve})
    for method in [engine.measure, engine.validate, engine.generate]:
        with pytest.raises(
            ValueError,
            match="floor3482" if reserve < 3482 else "independent completeness",
        ):
            method(request, parameters, control)
    assert loader.loads == loader.session.calls == 0

    engine.close(control)
    raw = cfg.model_dump()
    raw["long_context"]["baseline_output_reserve"] = 3482
    with pytest.raises(ValidationError):
        ActorEngineConfig.model_validate(raw)


def test_saved_json_actor_recipe_keeps_strict_tuple_json_semantics() -> None:
    saved = json.loads(config().model_dump_json())
    saved.update(
        schema_version="actor-engine-config/2",
        context_window=65536,
        long_context={"gpu_class": "a40"},
    )
    with pytest.raises(ValidationError):
        ActorEngineConfig.model_validate(saved)
    actual = ActorEngineConfig.model_validate_json(json.dumps(saved))
    assert (
        actual.long_context is not None
        and actual.long_context.baseline_output_reserve == 4096
    )
    assert actual.long_context.minimum_output_reserve == 3482 and isinstance(
        actual.packages, tuple
    )


@pytest.mark.parametrize("fraction", [0.8, 0.7225, None, True, "0.85"])
def test_long_reserve_fraction_is_frozen_to_original_baseline(fraction: object) -> None:
    raw = long_config().model_dump()
    raw["long_context"]["min_retained_fraction"] = fraction
    with pytest.raises(ValidationError):
        ActorEngineConfig.model_validate(raw)


def test_long_count_profile_binds_new_config_and_never_admits_reduced_reserve(
    tmp_path: Path,
) -> None:
    engine, loader, _, parameters, _ = setup(tmp_path)
    cfg = long_config()

    def ref(raw: bytes, schema: str) -> Any:
        return evidence_reference(
            raw,
            EvidenceMetadata(
                media_type="application/json",
                content_schema=schema,
                visibility="private",
                producer="unit-long-profile-pins",
            ),
        )

    binding = ActorModelBinding(
        model="Qwen2.5-7B-Instruct",
        release_ref=ref(b'{"unit_release_pin":true}', "release-manifest/1"),
        component_id="actor",
        model_artifact_id=engine.artifact.artifact_id,
        engine_config_artifact_id="actor-long-engine-config",
        engine_config_ref=ref(cfg.model_dump_json().encode(), "actor-engine-config/2"),
    )
    routing = ref(binding.model_dump_json().encode(), "model-binding/1")
    parameters = parameters.model_copy(
        update={"max_input_tokens": 61440, "max_new_tokens": 4096}
    )
    frozen = ref(parameters.model_dump_json().encode(), "model-parameters/1")
    profile = actor_budget_profile(
        engine.artifact, cfg, binding, routing, parameters, frozen, soft_target=24576
    )
    assert (
        profile.hard_limit == 61440
        and profile.output_reserve == 4096
        and profile.context_window == 65536
    )
    for reserve in [1536, 2048, 3481, 3482, 4095]:
        reduced = parameters.model_copy(update={"max_new_tokens": reserve})
        with pytest.raises(ValueError):
            actor_budget_profile(
                engine.artifact,
                cfg,
                binding,
                routing,
                reduced,
                ref(reduced.model_dump_json().encode(), "model-parameters/1"),
                soft_target=24576,
            )
    assert loader.loads == loader.session.calls == 0
    mismarked = binding.model_copy(
        update={
            "engine_config_ref": binding.engine_config_ref.model_copy(
                update={"content_schema": "actor-engine-config/1"}
            )
        }
    )
    with pytest.raises(OwnershipConflict):
        actor_budget_profile(
            engine.artifact,
            cfg,
            mismarked,
            ref(mismarked.model_dump_json().encode(), "model-binding/1"),
            parameters,
            frozen,
            soft_target=24576,
        )


def test_actor_release_ref_schema_must_equal_complete_config_body(
    tmp_path: Path,
) -> None:
    from actor_resource_fixtures import resource_case
    from actor_release_fixtures import metadata
    from lab_generate_skill.adapters.models.actor_release import verify_actor_release

    c = resource_case(tmp_path, Path("/not-launched/python"))
    original = ActorModelBinding.model_validate_json(
        c.evidence.read(c.spec.model_binding_ref)
    )
    wrong = c.evidence.put(
        c.evidence.read(original.engine_config_ref), metadata("actor-engine-config/2")
    )
    binding = original.model_copy(update={"engine_config_ref": wrong})
    ref = c.evidence.put(
        binding.model_dump_json().encode(), metadata("model-binding/1")
    )
    spec = c.spec.model_copy(update={"model_binding_ref": ref})
    with pytest.raises(OwnershipConflict):
        verify_actor_release(spec, c.evidence, c.workspace_root, c.controls.bind(c.op))
    assert not tuple(c.journal._root.iterdir())


def test_actual_frozen_engine2_publication_keeps_exact_version(tmp_path: Path) -> None:
    from actor_resource_fixtures import resource_case
    from actor_release_fixtures import freeze_model_release
    from lab_generate_skill.adapters.models.actor_release import verify_actor_release

    c = resource_case(tmp_path, Path("/not-launched/python"))
    cfg = long_config()
    release, binding_ref = freeze_model_release(
        c.workspace_root / "long-publication", c.evidence, c.spec.artifact, cfg
    )
    binding = ActorModelBinding.model_validate_json(c.evidence.read(binding_ref))
    assert (
        binding.engine_config_ref.content_schema
        == cfg.schema_version
        == "actor-engine-config/2"
    )
    spec = c.spec.model_copy(
        update={
            "release_ref": release,
            "model_binding_ref": binding_ref,
            "engine_config": cfg,
        }
    )
    actual = verify_actor_release(
        spec, c.evidence, c.workspace_root, c.controls.bind(c.op)
    )
    assert actual.engine_config == cfg and not tuple(c.journal._root.iterdir())
