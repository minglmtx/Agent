"""Reject a mismatched observed GPU before preparation; no CUDA or launch grant."""

import re
from lab_generate_skill.domain.actor_engine import ActorEngineConfig
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.slurm_allocation import SlurmAllocationObservation


def require_actor_allocation_identity(
    config: ActorEngineConfig, observation: SlurmAllocationObservation
) -> None:
    config = ActorEngineConfig.model_validate(config)
    observation = SlurmAllocationObservation.model_validate(observation)
    if config.schema_version != "actor-engine-config/2" or config.long_context is None:
        raise ValueError("Explicit qualified long Actor selection required")
    name = observation.facts.gpu.product_name.upper()
    slurm_type = observation.facts.controller.gpu_type.lower()
    target = config.long_context.gpu_class
    valid = False
    if target == "a40":
        valid = slurm_type == "a40" and name in ("NVIDIA A40", "A40")
    elif target in ("a100_40gb", "a100_80gb"):
        marker = "40GB" if target == "a100_40gb" else "80GB"
        valid = (
            slurm_type == "a100"
            and "A100" in name
            and re.search(r"(?<![0-9])" + marker + r"(?![0-9])", name) is not None
        )
    elif target == "rtx_pro_6000_blackwell":
        valid = (
            slurm_type == "rtxpro6k" and "RTX PRO 6000" in name and "BLACKWELL" in name
        )
    if not valid or "MIG" in name:
        raise EvidenceIntegrityError(
            "Actual allocated GPU differs from frozen Actor deployment"
        )
