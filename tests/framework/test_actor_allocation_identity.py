"""Actual allocation identity is checked before staging; never a CUDA grant."""

from pathlib import Path
from typing import Any, cast
import pytest
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.policies.actor_allocation_identity import (
    require_actor_allocation_identity,
)
from actor_long_fixtures import long_config
from allocation_fixtures import Case
from test_slurm_probe import operation


@pytest.mark.parametrize(
    "target,slurm_type,name",
    [
        ("a40", "a40", "NVIDIA A40"),
        ("a100_40gb", "a100", "NVIDIA A100-SXM4-40GB"),
        ("a100_80gb", "a100", "NVIDIA A100-SXM4-80GB"),
        (
            "rtx_pro_6000_blackwell",
            "rtxpro6k",
            "NVIDIA RTX PRO 6000 Blackwell Server Edition",
        ),
    ],
)
def test_exact_allocated_identity_can_be_consumed_without_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    slurm_type: str,
    name: str,
) -> None:
    c = Case(tmp_path, monkeypatch)
    original = c.verifier().observe(c.execution, c.writer, operation())
    observation = original.model_copy(
        update={
            "facts": original.facts.model_copy(
                update={
                    "gpu": original.facts.gpu.model_copy(update={"product_name": name}),
                    "controller": original.facts.controller.model_copy(
                        update={"gpu_type": slurm_type}
                    ),
                }
            )
        }
    )
    for _ in range(2):
        assert (
            cast(Any, require_actor_allocation_identity)(
                long_config(65536, target), observation
            )
            is None
        )
    assert c.kernel_calls == c.probe.calls == len(c.runner.calls) == 2


@pytest.mark.parametrize(
    "target,slurm_type,name",
    [
        ("a100_40gb", "a100", "NVIDIA A100-SXM4-80GB"),
        ("a100_80gb", "a100", "NVIDIA A100-SXM4-40GB"),
        ("a100_40gb", "a100", "NVIDIA A100-140GB"),
        ("a100_40gb", "a100", "NVIDIA A100-40GB MIG 1g.5gb"),
        ("a40", "a100", "NVIDIA A40"),
        ("a40", "a40", "NVIDIA RTX A6000"),
        ("rtx_pro_6000_blackwell", "rtxpro6k", "NVIDIA RTX PRO 6000 Ada"),
    ],
)
def test_wrong_observed_class_refuses_without_further_queries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    slurm_type: str,
    name: str,
) -> None:
    c = Case(tmp_path, monkeypatch)
    original = c.verifier().observe(c.execution, c.writer, operation())
    observation = original.model_copy(
        update={
            "facts": original.facts.model_copy(
                update={
                    "gpu": original.facts.gpu.model_copy(update={"product_name": name}),
                    "controller": original.facts.controller.model_copy(
                        update={"gpu_type": slurm_type}
                    ),
                }
            )
        }
    )
    with pytest.raises(EvidenceIntegrityError):
        require_actor_allocation_identity(long_config(65536, target), observation)
    assert len(c.runner.calls) == 2


@pytest.mark.parametrize("bad", [None, {}, [], True, "a40"])
def test_empty_or_wrong_type_is_not_allocation_evidence(bad: Any) -> None:
    with pytest.raises((ValueError, TypeError)):
        require_actor_allocation_identity(long_config(), bad)
