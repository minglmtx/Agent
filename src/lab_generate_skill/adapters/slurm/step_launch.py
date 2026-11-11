"""Pure fixed Generator GPU / browser and site CPU argv; no launch or execution permission."""

import hashlib
import json
from pathlib import PurePosixPath
from typing import Literal

from pydantic import TypeAdapter
from lab_generate_skill.domain.lifecycle import AllocationToken
from lab_generate_skill.domain.scheduler import SlurmExecutionIdentity
from lab_generate_skill.domain.slurm_allocation import NodeName


def _step_name(
    role: Literal["generator", "actor", "browser", "site", "training"],
    token: AllocationToken,
) -> str:
    token = AllocationToken.model_validate(token)
    raw = json.dumps(
        token.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return "lab-" + role + "-" + hashlib.sha256(raw).hexdigest()


def generator_step_name(token: AllocationToken) -> str:
    return _step_name("generator", token)


def browser_step_name(token: AllocationToken) -> str:
    return _step_name("browser", token)


def _executable(value: str) -> str:
    if type(value) is not str or not 1 <= len(value) <= 4096:
        raise ValueError("Step executable must be a bounded absolute path")
    path = PurePosixPath(value)
    if (
        not path.is_absolute()
        or str(path) != value
        or ".." in path.parts
        or "\0" in value
        or "\\" in value
        or any(ord(x) < 32 for x in value)
    ):
        raise ValueError("Step executable must be canonical absolute POSIX path")
    return value


def _fixed_step_argv(
    role: Literal["generator", "actor", "browser", "site", "training"],
    token: AllocationToken,
    execution: SlurmExecutionIdentity,
    node_id: str,
    *,
    python_executable: str,
    srun_executable: str,
) -> tuple[str, ...]:
    token = AllocationToken.model_validate(token)
    execution = SlurmExecutionIdentity.model_validate(execution)
    node_id = TypeAdapter(NodeName).validate_python(node_id, strict=True)
    python_executable, srun_executable = _executable(python_executable), _executable(
        srun_executable
    )
    if (
        token.scope != ("attempt" if role == "browser" else "batch")
        or token.resource_kind != ("trainer_model" if role == "training" else role)
        or token.provider_id
        != ("fixed-sft-worker" if role == "training" else "fixed-" + role + "-worker")
        or token.provider_version
        != {
            "browser": "3",
            "generator": "2",
            "actor": "1",
            "site": "6",
            "training": "1",
        }[role]
        or token.owner.job_id != execution.job_id
        or execution.job_id != execution.raw_job_id
    ):
        raise ValueError(
            "Fixed step requires its exact original allocation, scope and provider"
        )
    return (
        srun_executable,
        "--jobid=" + execution.job_id,
        "--job-name=" + _step_name(role, token),
        "--nodelist=" + node_id,
        "--exact",
        "--exclusive",
        "--nodes=1",
        "--ntasks=1",
        "--cpus-per-task=1",
        "--gres=gpu:1" if role in ("generator", "actor", "training") else "--gres=none",
        "--unbuffered",
        "--mpi=none",
        "--kill-on-bad-exit=1",
        "--immediate=5",
        "--export=ALL",
        python_executable,
        "-I",
        "-B",
        "-m",
        "lab_generate_skill.bootstrap." + role + "_worker",
    )


def fixed_generator_step_argv(
    token: AllocationToken,
    execution: SlurmExecutionIdentity,
    node_id: str,
    *,
    python_executable: str,
    srun_executable: str,
) -> tuple[str, ...]:
    """One original batch Generator, exactly one complete GPU."""
    return _fixed_step_argv(
        "generator",
        token,
        execution,
        node_id,
        python_executable=python_executable,
        srun_executable=srun_executable,
    )


def fixed_browser_step_argv(
    token: AllocationToken,
    execution: SlurmExecutionIdentity,
    node_id: str,
    *,
    python_executable: str,
    srun_executable: str,
) -> tuple[str, ...]:
    """One original attempt browser, CPU only even inside a GPU allocation."""
    return _fixed_step_argv(
        "browser",
        token,
        execution,
        node_id,
        python_executable=python_executable,
        srun_executable=srun_executable,
    )


def site_step_name(token: AllocationToken) -> str:
    return _step_name("site", token)


def fixed_site_step_argv(
    token: AllocationToken,
    execution: SlurmExecutionIdentity,
    node_id: str,
    *,
    python_executable: str,
    srun_executable: str,
) -> tuple[str, ...]:
    """One original batch site, CPU only; no site restore/launch permission."""
    return _fixed_step_argv(
        "site",
        token,
        execution,
        node_id,
        python_executable=python_executable,
        srun_executable=srun_executable,
    )


def actor_step_name(token: AllocationToken) -> str:
    return _step_name("actor", token)


def training_step_name(token: AllocationToken) -> str:
    return _step_name("training", token)


def fixed_training_step_argv(
    token: AllocationToken,
    execution: SlurmExecutionIdentity,
    node_id: str,
    *,
    python_executable: str,
    srun_executable: str,
) -> tuple[str, ...]:
    """One original trainer allocation, shared fixed GPU grammar, no permission."""
    return _fixed_step_argv(
        "training",
        token,
        execution,
        node_id,
        python_executable=python_executable,
        srun_executable=srun_executable,
    )


def fixed_actor_step_argv(
    token: AllocationToken,
    execution: SlurmExecutionIdentity,
    node_id: str,
    *,
    python_executable: str,
    srun_executable: str,
) -> tuple[str, ...]:
    """One original batch Actor, exactly one complete GPU."""
    return _fixed_step_argv(
        "actor",
        token,
        execution,
        node_id,
        python_executable=python_executable,
        srun_executable=srun_executable,
    )
