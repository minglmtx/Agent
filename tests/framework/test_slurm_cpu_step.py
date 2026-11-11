"""Observed CPU layout; exact role selection, no GPU fallback or authority claim."""

import hashlib
import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.slurm.step_codec import parse_step_json
from lab_generate_skill.adapters.slurm.step_text import check_step_text
from lab_generate_skill.adapters.slurm.step_launch import (
    fixed_browser_step_argv,
    fixed_generator_step_argv,
    browser_step_name,
)
from lab_generate_skill.domain.slurm_step import SlurmStepTarget, SlurmControllerStep
from lab_generate_skill.domain.lifecycle import AllocationToken
from slurm_step_fixtures import target, token, encoded

FIXTURES = Path(__file__).parent / "fixtures/slurm-cpu-step-4760011"


def cpu_target() -> SlurmStepTarget:
    """Controller fields from probe; kernel fields deliberately synthetic."""
    old = target()
    execution = old.execution.model_copy(
        update={
            "job_id": "4760011",
            "raw_job_id": "4760011",
            "submitted_at_epoch": 1793084500,
            "started_at_epoch": 1793084510,
        }
    )
    launcher = old.launcher.model_copy(
        update={"node_id": "a0325", "process_id": 2277365}
    )
    return SlurmStepTarget(
        execution=execution,
        step_name="lab-browser-cpu-probe",
        resources="cpu_only",
        launcher=launcher,
        worker=old.worker.model_copy(
            update={
                "job_id": execution.job_id,
                "writer": launcher.model_copy(update={"process_id": 2277387}),
                "user_path": old.worker.user_path.replace("4752096", "4760011"),
            }
        ),
    )


def cpu_data() -> dict[str, Any]:
    result: Any = json.loads((FIXTURES / "live.json").read_bytes())
    assert isinstance(result, dict)
    return result


def cpu_text() -> bytes:
    # Preserve recorded bytes; observer requests epoch format in live queries.
    return (
        (FIXTURES / "live.txt")
        .read_bytes()
        .replace(
            b"StartTime=2026-10-27T08:01:56",
            b"StartTime=1793084516",
        )
    )


def browser_token() -> AllocationToken:
    return AllocationToken.model_validate(
        token().model_copy(
            update={
                "scope": "attempt",
                "attempt_id": "attempt",
                "resource_kind": "browser",
                "provider_id": "fixed-browser-worker",
                "provider_version": "3",
                "expected_resource_id": "browser",
            }
        )
    )


def test_recorded_cpu_layout_roundtrip_and_repeat() -> None:
    provenance = json.loads((FIXTURES / "provenance.json").read_bytes())
    for name, identity in provenance["files"].items():
        raw = (FIXTURES / name).read_bytes()
        assert len(raw) == identity["size_bytes"]
        assert hashlib.sha256(raw).hexdigest() == identity["sha256"]
    raw = (FIXTURES / "live.json").read_bytes()
    first = parse_step_json(raw, cpu_target())
    assert first.gpu_type is None and first.memory == "3750M"
    assert first.target.resources == "cpu_only" and first.started_at_epoch == 1793084516
    assert parse_step_json(raw, cpu_target()) == first
    assert SlurmControllerStep.model_validate_json(first.model_dump_json()) == first
    check_step_text(cpu_text(), first)


@pytest.mark.parametrize("profile", [None, "", "auto", "cpu", True, 1, []])
def test_profile_must_be_explicit_and_supported(profile: Any) -> None:
    data = cpu_target().model_dump()
    data["resources"] = profile
    with pytest.raises(ValueError):
        SlurmStepTarget.model_validate(data)


def test_no_legacy_default_or_cross_profile_fallback() -> None:
    data = cpu_target().model_dump()
    del data["resources"]
    with pytest.raises(ValueError):
        SlurmStepTarget.model_validate(data)
    data["resources"] = "cpu_only"
    data["schema_version"] = "slurm-step-target/1"
    with pytest.raises(ValueError):
        SlurmStepTarget.model_validate(data)
    with pytest.raises(ValueError):
        parse_step_json(
            encoded(cpu_data()),
            cpu_target().model_copy(update={"resources": "single_gpu"}),
        )
    from slurm_step_fixtures import recorded

    with pytest.raises(ValueError):
        parse_step_json(
            encoded(recorded()), target().model_copy(update={"resources": "cpu_only"})
        )
    result = parse_step_json(encoded(cpu_data()), cpu_target())
    with pytest.raises(ValueError):
        SlurmControllerStep.model_validate(
            result.model_copy(update={"gpu_type": "a40"})
        )
    with pytest.raises(ValueError):
        SlurmControllerStep.model_validate(
            result.model_copy(update={"schema_version": "slurm-controller-step/1"})
        )
    gpu = parse_step_json(encoded(recorded()), target())
    with pytest.raises(ValueError):
        SlurmControllerStep.model_validate(gpu.model_copy(update={"gpu_type": None}))


@pytest.mark.parametrize(
    "allocation",
    [
        "",
        None,
        [],
        True,
        "cpu=1,node=1",
        "cpu=2,mem=3750M,node=1",
        "cpu=1,mem=3750M,node=2",
        "cpu=1,mem=0,node=1",
        "cpu=1,mem=-1M,node=1",
        "cpu=1,mem=3750M,node=1,cpu=1",
        "cpu=1,mem=3750M,node=1,gres/gpu=0",
        "cpu=1,mem=3750M,node=1,gres/gpu=1,gres/gpu:a40=1",
        "cpu=1,mem=3750M,node=1,gres/shard=1",
        "cpu=1,mem=3750M,node=1,",
    ],
)
def test_cpu_resource_corruption_rejected(allocation: Any) -> None:
    data = cpu_data()
    data["steps"][0]["tres"]["allocation"] = allocation
    with pytest.raises(ValueError):
        parse_step_json(encoded(data), cpu_target())


@pytest.mark.parametrize(
    "field,value", [("node", "gres/gpu:1"), ("task", "cpu=2,cpu:2"), ("cpu", None)]
)
def test_cpu_per_resource_mismatch_rejected(field: str, value: Any) -> None:
    data = cpu_data()
    data["steps"][0]["tres"]["per"][field] = value
    with pytest.raises(ValueError):
        parse_step_json(encoded(data), cpu_target())


@pytest.mark.parametrize(
    "before,after",
    [
        (b"TRES=cpu=1", b"TRES=cpu=1,gres/gpu=1"),
        (b"TresPerStep=cpu:1", b"TresPerStep=cpu:1 TresPerNode=gres/gpu:1"),
        (b"TresPerStep=cpu:1", b"TresPerStep=cpu:1 TresPerNode="),
        (b"mem=3750M", b"mem=3751M"),
        (b"CPUs=1", b"CPUs=2"),
    ],
)
def test_cpu_text_cross_check_rejects_resources(before: bytes, after: bytes) -> None:
    with pytest.raises(ValueError):
        check_step_text(
            cpu_text().replace(before, after),
            parse_step_json(encoded(cpu_data()), cpu_target()),
        )


def test_browser_argv_is_fixed_cpu_only_and_deterministic() -> None:
    t, b = target(), browser_token()
    argv = fixed_browser_step_argv(
        b,
        t.execution,
        t.launcher.node_id,
        python_executable="/workspace/python",
        srun_executable="/usr/bin/srun",
    )
    assert argv[-5:] == (
        "/workspace/python",
        "-I",
        "-B",
        "-m",
        "lab_generate_skill.bootstrap.browser_worker",
    )
    assert "--gres=none" in argv and "--gres=gpu:1" not in argv
    assert "--job-name=" + browser_step_name(b) in argv
    assert "--exact" in argv and "--exclusive" in argv
    assert argv == fixed_browser_step_argv(
        b,
        t.execution,
        t.launcher.node_id,
        python_executable="/workspace/python",
        srun_executable="/usr/bin/srun",
    )
    assert browser_step_name(b) != browser_step_name(
        b.model_copy(update={"attempt_id": "other"})
    )


@pytest.mark.parametrize(
    "change",
    [
        {"scope": "batch", "attempt_id": None},
        {"resource_kind": "generator"},
        {"provider_id": "fixed-generator-worker"},
        {"provider_version": "1"},
        {"provider_version": "2"},
        {"owner": token().owner.model_copy(update={"job_id": "other"})},
    ],
)
def test_browser_argv_rejects_foreign_scope_or_provider(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        fixed_browser_step_argv(
            browser_token().model_copy(update=change),
            target().execution,
            "a0535",
            python_executable="/workspace/python",
            srun_executable="/usr/bin/srun",
        )


def test_generator_does_not_accept_browser_allocation() -> None:
    with pytest.raises(ValueError):
        fixed_generator_step_argv(
            browser_token(),
            target().execution,
            "a0535",
            python_executable="/workspace/python",
            srun_executable="/usr/bin/srun",
        )


@pytest.mark.parametrize("version", ["1", "3", "unknown"])
def test_generator_requires_current_provider_version(version: str) -> None:
    with pytest.raises(ValueError):
        fixed_generator_step_argv(
            token().model_copy(update={"provider_version": version}),
            target().execution,
            "a0535",
            python_executable="/workspace/python",
            srun_executable="/usr/bin/srun",
        )
