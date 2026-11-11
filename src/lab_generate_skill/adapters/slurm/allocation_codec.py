"""Pure, bounded controller decoding for the observed v0.0.44 deployment.

Only one running scalar job on one node with one typed full GPU is supported.
Unknown layouts fail closed. Callers retain raw bytes and separately verify
accounting DBIndex, OS/cgroup ownership, device identity and query freshness.
"""

import re
from typing import Any

from lab_generate_skill.domain.scheduler import SlurmExecutionIdentity
from lab_generate_skill.domain.slurm_allocation import SlurmControllerAllocation
from lab_generate_skill.adapters.processes.wire_json import json_object

CONTROLLER_MAX_BYTES = 1024 * 1024
_GPU = re.compile(r"gpu:([A-Za-z0-9][A-Za-z0-9_-]{0,63}):1\(IDX:(0|[1-9][0-9]{0,6})\)")


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Controller field must be an object")
    return value


def _integer(value: object) -> int:
    if type(value) is not int:
        raise ValueError("Controller field must be an exact integer")
    return value


def _number(value: object, *, is_set: bool = True) -> int:
    record = _object(value)
    if (
        set(record) != {"set", "infinite", "number"}
        or record["set"] is not is_set
        or record["infinite"] is not False
    ):
        raise ValueError("Controller number has unknown or infinite value")
    return _integer(record["number"])


def parse_controller_allocation(
    raw: bytes, execution: SlurmExecutionIdentity, node_id: str
) -> SlurmControllerAllocation:
    """Match original identity, without IO or deriving execution authority."""
    execution = SlurmExecutionIdentity.model_validate(execution)
    if type(raw) is not bytes:
        raise TypeError("Controller output must be bytes")
    if not 0 < len(raw) <= CONTROLLER_MAX_BYTES:
        raise ValueError("Controller output exceeds byte bounds")
    if "_" in execution.job_id:
        raise ValueError("Array allocations are not supported by this deployment")
    try:
        data = json_object(raw)
    except RecursionError as error:
        raise ValueError("Controller JSON nesting exceeds decoder capacity") from error
    if data.get("errors") != [] or data.get("warnings") != []:
        raise ValueError("Controller returned errors or warnings")
    meta = _object(data.get("meta"))
    if _object(meta.get("plugin")).get("data_parser") != "data_parser/v0.0.44":
        raise ValueError("Unverified Slurm controller data parser")
    if _object(meta.get("slurm")).get("cluster") != execution.cluster:
        raise ValueError("Controller cluster differs from original execution")
    jobs = data.get("jobs")
    if type(jobs) is not list or len(jobs) != 1:
        raise ValueError("Controller must return exactly one allocation")
    job = _object(jobs[0])
    if (
        job.get("cluster") != execution.cluster
        or _integer(job.get("job_id")) != int(execution.raw_job_id)
        or _integer(job.get("user_id")) != execution.uid
        or _integer(job.get("restart_cnt")) != execution.restart_count
        or _number(job.get("submit_time")) != execution.submitted_at_epoch
        or _number(job.get("start_time")) != execution.started_at_epoch
        or job.get("job_state") != ["RUNNING"]
    ):
        raise ValueError("Controller does not match the original running execution")
    if (
        _number(job.get("array_job_id")) != 0
        or _number(job.get("array_task_id"), is_set=False) != 0
        or _number(job.get("het_job_id")) != 0
    ):
        raise ValueError("Array or heterogeneous allocation is unsupported")
    nodes = _object(_object(job.get("job_resources")).get("nodes"))
    allocations = nodes.get("allocation")
    if (
        type(node_id) is not str
        or job.get("nodes") != node_id
        or job.get("batch_host") != node_id
        or nodes.get("list") != node_id
        or _integer(nodes.get("count")) != 1
        or type(allocations) is not list
        or len(allocations) != 1
        or _object(allocations[0]).get("name") != node_id
        or _integer(_object(allocations[0]).get("index")) != 0
    ):
        raise ValueError("Controller must allocate exactly the writer node")
    gres = job.get("gres_detail")
    if type(gres) is not list or len(gres) != 1 or type(gres[0]) is not str:
        raise ValueError("Controller must report one full GPU assignment")
    match = _GPU.fullmatch(gres[0])
    if match is None:
        raise ValueError("Unsupported GPU assignment layout")
    return SlurmControllerAllocation(
        job_id=execution.raw_job_id,
        node_id=node_id,
        gpu_type=match[1],
        gpu_index=int(match[2]),
    )
