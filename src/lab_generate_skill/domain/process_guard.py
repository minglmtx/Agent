"""Observed direct-child supervision, not descendant termination or authority."""

from typing import Literal, Self
from pydantic import model_validator
from .validation import Contract
from .process_identity import ProcessIdentity


class ProcessOwnerGuard(Contract):
    schema_version: Literal["process-owner-guard/1"] = "process-owner-guard/1"
    controller: ProcessIdentity
    supervisor: ProcessIdentity
    worker: ProcessIdentity
    parent_death_signal: Literal["SIGKILL"] = "SIGKILL"

    @model_validator(mode="after")
    def distinct_original_processes(self) -> Self:
        values = (self.controller, self.supervisor, self.worker)
        if (
            len({p.process_id for p in values}) != 3
            or len({(p.node_id, p.boot_id) for p in values}) != 1
        ):
            raise ValueError("Guard requires three distinct processes on one host boot")
        return self
