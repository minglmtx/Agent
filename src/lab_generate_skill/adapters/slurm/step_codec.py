"""Bounded v0.0.44 JSON step facts; accept only the observed null sentinel warning."""

import re
from typing import Any

from lab_generate_skill.adapters.processes.wire_json import json_object
from lab_generate_skill.domain.slurm_step import SlurmStepTarget, SlurmControllerStep

STEP_MAX_BYTES = 1024 * 1024
NULL_WARNING = [
    {"description": "Dumping (0xfffffffe) as place holder for null", "source": ""}
]
ABSENT_WARNING = [{"description": "Zero steps to dump", "source": ""}]


def _object(value: object) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError("Step field must be a JSON object")
    return value


def _integer(value: object) -> int:
    if type(value) is not int:
        raise ValueError("Step field must be an exact integer")
    return value


def _envelope(raw: bytes, target: SlurmStepTarget) -> dict[str, Any]:
    if type(raw) is not bytes:
        raise TypeError("Step JSON must be bytes")
    if not 0 < len(raw) <= STEP_MAX_BYTES:
        raise ValueError("Step JSON exceeds byte bounds")
    try:
        data = json_object(raw)
    except RecursionError as error:
        raise ValueError("Step JSON nesting exceeds decoder capacity") from error
    if data.get("errors") != []:
        raise ValueError("Step controller reported errors")
    meta = _object(data.get("meta"))
    if (
        _object(meta.get("plugin")).get("data_parser") != "data_parser/v0.0.44"
        or _object(meta.get("slurm")).get("cluster") != target.execution.cluster
    ):
        raise ValueError("Step controller parser or cluster differs")
    return data


def parse_step_json(raw: bytes, target: SlurmStepTarget) -> SlurmControllerStep:
    target = SlurmStepTarget.model_validate(target)
    data = _envelope(raw, target)
    steps = data.get("steps")
    if type(steps) is not list or len(steps) != 1:
        raise ValueError("Exactly one original running step is required")
    step = _object(steps[0])
    array = _object(step.get("array"))
    if (
        set(array) != {"job_id", "task_id"}
        or _integer(array.get("job_id")) != 0
        or _integer(array.get("task_id")) != 4294967294
        or data.get("warnings") != NULL_WARNING
    ):
        raise ValueError("Unsupported step array identity or controller warning")
    srun = _object(step.get("srun"))
    if (
        step.get("id") != target.step_key
        or step.get("cluster") != target.execution.cluster
        or step.get("name") != target.step_name
        or step.get("nodes") != target.launcher.node_id
        or step.get("state") != ["RUNNING"]
        or srun.get("host") != target.launcher.node_id
        or _integer(srun.get("pid")) != target.launcher.process_id
    ):
        raise ValueError("Controller differs from original step/launcher identity")
    if (
        _integer(step.get("number_cpus")) != 1
        or _integer(step.get("number_tasks")) != 1
        or step.get("container") != ""
        or step.get("container_id") != ""
    ):
        raise ValueError("Unsupported step task/CPU/container layout")
    start = _object(_object(step.get("time")).get("start"))
    if (
        set(start) != {"set", "infinite", "number"}
        or start["set"] is not True
        or start["infinite"] is not False
    ):
        raise ValueError("Step start time must be a known finite epoch")
    tres = _object(step.get("tres"))
    if tres.get("per") != {
        "cpu": "",
        "memory": "",
        "step": "cpu:1",
        "node": "gres/gpu:1" if target.resources == "single_gpu" else "",
        "socket": "",
        "task": "cpu=1,cpu:1",
    }:
        raise ValueError("Unsupported per-step resource layout")
    allocation = tres.get("allocation")
    if type(allocation) is not str:
        raise ValueError("Step resources must be an allocation string")
    values: dict[str, str] = {}
    for pair in allocation.split(","):
        key, sep, value = pair.partition("=")
        if not sep or key in values:
            raise ValueError("Malformed or duplicate step resource")
        values[key] = value
    gpu_type: str | None = None
    if target.resources == "cpu_only":
        if set(values) != {"cpu", "node", "mem"} or any(
            values[key] != "1" for key in ("cpu", "node")
        ):
            raise ValueError(
                "CPU step must have one CPU/node and no GPU or other resource"
            )
    else:
        gpu = [
            key
            for key in values
            if re.fullmatch(r"gres/gpu:[A-Za-z0-9][A-Za-z0-9_-]{0,63}", key)
        ]
        if (
            len(gpu) != 1
            or set(values) != {"cpu", "node", "mem", "gres/gpu", gpu[0]}
            or any(values[key] != "1" for key in ("cpu", "node", "gres/gpu", gpu[0]))
        ):
            raise ValueError("Step must have one CPU/node and one complete typed GPU")
        gpu_type = gpu[0][len("gres/gpu:") :]
    return SlurmControllerStep(
        target=target,
        started_at_epoch=_integer(start["number"]),
        gpu_type=gpu_type,
        memory=values["mem"],
    )


def check_step_absent(raw: bytes, target: SlurmStepTarget) -> None:
    """Validate an empty reply to an exact step query, NOT resource termination."""
    target = SlurmStepTarget.model_validate(target)
    data = _envelope(raw, target)
    if data.get("steps") != [] or data.get("warnings") != ABSENT_WARNING:
        raise ValueError("Controller did not return the explicit empty-step result")
