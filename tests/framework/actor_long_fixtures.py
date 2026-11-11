"""Synthetic CUDA/Transformers objects; no real hardware or long-run qualification."""

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import copy
import importlib
import pytest
from lab_generate_skill.domain.actor_engine import ActorEngineConfig
from actor_engine_fixtures import config


def long_config(window: int = 65536, gpu: str = "a40") -> ActorEngineConfig:
    raw = config().model_dump()
    raw.update(
        schema_version="actor-engine-config/2",
        context_window=window,
        long_context={
            "gpu_class": gpu,
        },
    )
    return ActorEngineConfig.model_validate(raw)


def cuda_runtime(name: str = "NVIDIA A40", memory: int = 46, sms: int = 84) -> Any:
    props = SimpleNamespace(
        name=name,
        total_memory=memory * 1024**3,
        multi_processor_count=sms,
        uuid="GPU-unit-only",
    )
    return SimpleNamespace(
        cuda=SimpleNamespace(
            is_available=lambda: True,
            device_count=lambda: 1,
            get_device_properties=lambda _: props,
            empty_cache=lambda: None,
            get_device_capability=lambda _: (12, 0),
            get_arch_list=lambda: ["sm_120"],
        ),
        version=SimpleNamespace(cuda="12.8"),
        set_num_threads=lambda _: None,
        _C=SimpleNamespace(_cuda_clearCublasWorkspaces=lambda: None),
    )


def loader_modules(monkeypatch: pytest.MonkeyPatch, *, legacy: bool = False) -> Any:

    torch = cuda_runtime()
    original_config = SimpleNamespace(
        model_type="qwen2", max_position_embeddings=32768, rope_scaling=None
    )
    calls: dict[str, Any] = {
        "loads": 0,
        "auto_configs": 0,
        "closed": 0,
        "workspaces_cleared": 0,
    }

    def auto_config(root: str, **options: Any) -> Any:
        assert options == {"local_files_only": True, "trust_remote_code": False}
        calls["auto_configs"] += 1
        return copy.deepcopy(original_config)

    def load(root: str, **options: Any) -> Any:
        calls["loads"] += 1
        calls["load_options"] = options
        loaded = options.get("config", copy.deepcopy(original_config))
        loaded._attn_implementation = options.get(
            "attn_implementation", "standard-unmodified"
        )
        return SimpleNamespace(
            config=loaded,
            generation_config=SimpleNamespace(eos_token_id=[2]),
            eval=lambda: None,
        )

    transformer = SimpleNamespace(
        AutoConfig=SimpleNamespace(from_pretrained=auto_config),
        AutoModelForCausalLM=SimpleNamespace(from_pretrained=load),
        AutoTokenizer=SimpleNamespace(
            from_pretrained=lambda *a, **kw: SimpleNamespace(eos_token_id=2)
        ),
    )
    torch.bfloat16 = "unit-bfloat16"

    def empty() -> None:
        calls["closed"] += 1

    torch.cuda.empty_cache = empty

    def clear_workspaces() -> None:
        calls["workspaces_cleared"] += 1

    torch._C._cuda_clearCublasWorkspaces = clear_workspaces
    original_import = importlib.import_module

    def imported(name: str, *args: Any, **kwargs: Any) -> Any:
        return (
            torch
            if name == "torch"
            else (
                transformer
                if name == "transformers"
                else original_import(name, *args, **kwargs)
            )
        )

    monkeypatch.setattr(importlib, "import_module", imported)
    return SimpleNamespace(
        torch=torch, transformer=transformer, original=original_config, calls=calls
    )
