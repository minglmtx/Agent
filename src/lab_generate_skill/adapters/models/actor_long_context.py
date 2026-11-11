"""Concrete CUDA class checks before long Actor allocation; no partition guessing."""

from typing import Any
from lab_generate_skill.domain.actor_engine import ActorEngineConfig
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from .causal_session import CausalPositionOverride


def actor_position_override(
    config: ActorEngineConfig, torch: Any
) -> CausalPositionOverride:
    config = ActorEngineConfig.model_validate(config)
    long = config.long_context
    if config.schema_version != "actor-engine-config/2" or long is None:
        raise ValueError("Explicit Actor long configuration required")
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise EvidenceIntegrityError("Long Actor requires exactly one visible CUDA GPU")
    props = torch.cuda.get_device_properties(0)
    name = str(props.name).upper()
    uuid = str(getattr(props, "uuid", "")).upper()
    if "MIG" in name or "MIG" in uuid:
        raise EvidenceIntegrityError(
            "MIG is not a qualified full GPU long Actor target"
        )
    memory, sms = props.total_memory, props.multi_processor_count
    if type(memory) is not int or type(sms) is not int:
        raise EvidenceIntegrityError("Concrete complete GPU capacity facts required")
    target = long.gpu_class
    valid = False
    if target == "a40":
        valid = name in ("NVIDIA A40", "A40") and sms >= 84 and memory >= 42 * 1024**3
    elif target in ("a100_40gb", "a100_80gb"):
        marker, minimum, maximum = (
            ("40GB", 36, 48) if target == "a100_40gb" else ("80GB", 72, 88)
        )
        valid = (
            "A100" in name
            and marker in name
            and sms >= 108
            and minimum * 1024**3 <= memory <= maximum * 1024**3
        )
    elif target == "rtx_pro_6000_blackwell":
        cuda = str(torch.version.cuda or "").split(".")
        compatible = (
            len(cuda) >= 2
            and all(x.isdigit() for x in cuda[:2])
            and tuple(int(x) for x in cuda[:2]) >= (12, 8)
        )
        capability = torch.cuda.get_device_capability(0)
        arch = "sm_" + str(capability[0]) + str(capability[1])
        valid = (
            "RTX PRO 6000" in name
            and "BLACKWELL" in name
            and memory >= 88 * 1024**3
            and compatible
            and arch in torch.cuda.get_arch_list()
        )
    if not valid:
        raise EvidenceIntegrityError(
            "Actual GPU/runtime differs from frozen Actor long resource class"
        )
    return CausalPositionOverride(
        original_window=32768,
        maximum_window=131072,
        rope_scaling={
            "rope_type": "yarn",
            "factor": 4.0,
            "original_max_position_embeddings": 32768,
        },
        attention_backend="sdpa",
    )
