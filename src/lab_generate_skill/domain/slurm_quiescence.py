"""Original numeric step user-tree observation, not resource-release authority."""

from typing import Literal, Self
from pydantic import Field, model_validator

from .process_identity import ProcessIdentity
from .slurm_allocation import SlurmCgroupMembership
from .validation import Contract


class SlurmUserEnding(Contract):
    original: SlurmCgroupMembership
    observer: ProcessIdentity
    writer_status: Literal["missing", "reused"]
    replacement_start_ticks: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def original_host_and_incarnation(self) -> Self:
        writer = self.original.writer
        if self.original.step_id == "batch":
            raise ValueError("Quiescence requires an original dedicated numeric step")
        if (self.observer.node_id, self.observer.boot_id) != (
            writer.node_id,
            writer.boot_id,
        ):
            raise ValueError(
                "Original user subtree must be observed on the same host boot"
            )
        if self.writer_status == "missing":
            if (
                self.replacement_start_ticks is not None
                or self.observer.process_id == writer.process_id
            ):
                raise ValueError(
                    "Missing original process cannot identify a replacement or observer"
                )
        elif (
            self.replacement_start_ticks is None
            or self.replacement_start_ticks == writer.start_ticks
        ):
            raise ValueError("Reused PID requires a different positive start time")
        if (
            self.observer.process_id == writer.process_id
            and self.observer.start_ticks != self.replacement_start_ticks
        ):
            raise ValueError("Observer reused PID must match its observed incarnation")
        return self


class SlurmUserQuiescence(SlurmUserEnding):
    schema_version: Literal["slurm-user-quiescence/1"] = "slurm-user-quiescence/1"


class SlurmUserRemoval(SlurmUserEnding):
    """Original live-pinned cgroup directory and events were kernel-offlined.

    Not inferred from path absence: adapter must retain and verify both handles,
    original inode/device/mount, deleted fd link and events ENODEV.
    """

    schema_version: Literal["slurm-user-removal/1"] = "slurm-user-removal/1"
