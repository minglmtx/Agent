"""Original browser CPU-step binding and observed facts; never permissions."""

from typing import Literal, Self
from pydantic import model_validator
from .validation import Contract
from .slurm_binding import ScalarBatchBinding
from .worker_processes import CpuProcessStopFacts
from .slurm_step import SlurmStepTarget, SlurmControllerStep
from .slurm_quiescence import SlurmUserQuiescence, SlurmUserRemoval
from .evidence import EvidenceRef
from .state_scope import private_state_ref


class BrowserSlurmBinding(ScalarBatchBinding):
    schema_version: Literal["browser-slurm-binding/1"] = "browser-slurm-binding/1"


class BrowserStepStarted(Contract):
    schema_version: Literal["browser-step-started/1"] = "browser-step-started/1"
    controller: SlurmControllerStep
    evidence: EvidenceRef

    @model_validator(mode="after")
    def cpu_facts(self) -> Self:
        if self.controller.target.resources != "cpu_only":
            raise ValueError("Browser step cannot acquire a GPU")
        private_state_ref(self.evidence, "browser-step-raw/1")
        return self


class BrowserStepClosed(Contract):
    schema_version: Literal["browser-step-closed/1"] = "browser-step-closed/1"
    target: SlurmStepTarget
    quiescence: SlurmUserQuiescence | SlurmUserRemoval
    evidence: EvidenceRef

    @model_validator(mode="after")
    def original_tree(self) -> Self:
        if (
            self.target.resources != "cpu_only"
            or self.quiescence.original != self.target.worker
        ):
            raise ValueError("Browser closure changed its original CPU step")
        private_state_ref(self.evidence, "browser-step-raw/1")
        return self


class BrowserProcessStop(CpuProcessStopFacts):
    schema_version: Literal["browser-process-stop/1"] = "browser-process-stop/1"
