"""Readonly allocation facts; neither admission nor termination permission.

Controller facts omit DBIndex: that identity must independently be checked by
the accounting probe. Device numbers are physical Linux minors, never CUDA's
process-local ordinals. Kernel membership and combined observation follow in
the same allocation module increment.
"""

from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from .scheduler import SlurmExecutionIdentity, SlurmJobObservation, SlurmNumber
from .evidence import EvidenceRef
from .process_identity import ProcessIdentity
from .validation import Contract

NodeName = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,252}$")
]


class SlurmControllerAllocation(Contract):
    schema_version: Literal["slurm-controller-allocation/1"] = (
        "slurm-controller-allocation/1"
    )
    job_id: SlurmNumber
    node_id: NodeName
    gpu_type: Annotated[
        str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    ]
    gpu_index: int = Field(ge=0, le=1048575)


class SlurmGpuDevice(Contract):
    schema_version: Literal["slurm-gpu-device/1"] = "slurm-gpu-device/1"
    uuid: Annotated[
        str,
        StringConstraints(
            pattern=r"^GPU-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        ),
    ]
    pci_bus_id: Annotated[
        str,
        StringConstraints(pattern=r"^[0-9A-F]{8}:[0-9A-F]{2}:[0-1][0-9A-F]\.[0-7]$"),
    ]
    minor_number: int = Field(ge=0, le=1048575)
    product_name: Annotated[
        str, StringConstraints(min_length=1, max_length=128, pattern=r"^[ -~]+$")
    ]


class SlurmCgroupMembership(Contract):
    """Current local writer observed in its root-managed Slurm user subtree.

    Records the original subtree inode and inspecting observer's mount ID for
    later independent observation in that mount view. A foreign worker can have
    a distinct mount ID for the same full cgroup filesystem. This
    record does not grant acquisition, takeover or permission to signal a PID.
    """

    schema_version: Literal["slurm-cgroup-membership/1"] = "slurm-cgroup-membership/1"
    job_id: SlurmNumber
    step_id: Annotated[str, StringConstraints(pattern=r"^(batch|0|[1-9][0-9]{0,9})$")]
    writer: ProcessIdentity
    uid: int = Field(gt=0, le=4294967294)
    user_path: str
    mount_id: int = Field(gt=0)
    device: int = Field(ge=0)
    user_inode: int = Field(gt=0)
    task_inode: int = Field(gt=0)

    @model_validator(mode="after")
    def exact_subtree(self) -> Self:
        expected = (
            "/sys/fs/cgroup/system.slice/slurmstepd.scope/job_"
            + self.job_id
            + "/step_"
            + self.step_id
            + "/user"
        )
        if self.user_path != expected or self.user_inode == self.task_inode:
            raise ValueError(
                "Cgroup identity must name the exact distinct user/task roots"
            )
        return self


class SlurmAllocationFacts(Contract):
    """Consistent current observations, without acquisition or request authority."""

    schema_version: Literal["slurm-allocation-facts/1"] = "slurm-allocation-facts/1"
    execution: SlurmExecutionIdentity
    writer: ProcessIdentity
    observed_at: AwareDatetime
    accounting_before: SlurmJobObservation
    accounting_after: SlurmJobObservation
    controller: SlurmControllerAllocation
    gpu: SlurmGpuDevice
    cgroup: SlurmCgroupMembership

    @model_validator(mode="after")
    def matched_original_allocation(self) -> Self:
        for observation in (self.accounting_before, self.accounting_after):
            if (
                observation.execution != self.execution
                or observation.accounting_state != "RUNNING"
                or observation.queue_state != "RUNNING"
                or observation.ended_at_epoch is not None
                or observation.exit_status != 0
                or observation.exit_signal != 0
            ):
                raise ValueError(
                    "Allocation requires the original running accounting/queue observations"
                )
        if (
            not self.accounting_before.observed_at
            <= self.accounting_after.observed_at
            <= self.observed_at
        ):
            raise ValueError("Allocation observations are not chronologically ordered")
        if (
            self.execution.job_id != self.execution.raw_job_id
            or self.controller.job_id != self.execution.raw_job_id
            or self.controller.node_id != self.writer.node_id
            or self.controller.gpu_index != self.gpu.minor_number
            or self.cgroup.writer != self.writer
            or self.cgroup.job_id != self.execution.raw_job_id
            or self.cgroup.uid != self.execution.uid
        ):
            raise ValueError("Controller, GPU and kernel identities do not match")
        return self


class SlurmAllocationObservation(Contract):
    schema_version: Literal["slurm-allocation-observation/1"] = (
        "slurm-allocation-observation/1"
    )
    facts: SlurmAllocationFacts
    evidence: EvidenceRef

    @model_validator(mode="after")
    def private_raw_evidence(self) -> Self:
        if (
            self.evidence.visibility != "private"
            or self.evidence.content_schema != "slurm-allocation-raw/1"
        ):
            raise ValueError(
                "Allocation observations require private versioned raw evidence"
            )
        return self
