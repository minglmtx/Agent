"""Pure finite SFT call contract; persistence and dispatch are separate ports."""

import hashlib
from typing import Literal, Self
from pydantic import Field, model_validator
from .validation import Contract, Identifier, Sha256
from .training_worker import TrainingWorkerConfiguration
from .process_identity import ProcessIdentity

MAX_PACKET = 16 * 1024**2
Operation = Literal["configure", "train", "close"]


class TrainingWorkerCommand(Contract):
    schema_version: Literal["sft-worker-command/1"] = "sft-worker-command/1"
    session_id: Identifier
    sequence: int = Field(ge=1, le=3)
    operation: Operation
    remaining_seconds: float = Field(gt=0, le=86400, allow_inf_nan=False)
    controller: ProcessIdentity | None = None
    configuration: TrainingWorkerConfiguration | None = None
    contract_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def shape(self) -> Self:
        if (self.controller is not None) != (self.operation == "configure") or (
            self.configuration is not None
        ) != (self.operation == "configure"):
            raise ValueError("Only configure carries original controller/configuration")
        if (self.contract_sha256 is not None) != (self.operation == "train"):
            raise ValueError("Only train carries the original complete contract digest")
        if (
            (self.operation == "configure" and self.sequence != 1)
            or (self.operation == "train" and self.sequence != 2)
            or (self.operation == "close" and self.sequence not in (2, 3))
        ):
            raise ValueError("Finite configure/train-once/close sequence required")
        if len(self.model_dump_json().encode()) > MAX_PACKET:
            raise ValueError("Training command exceeds wire bound")
        return self

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()
