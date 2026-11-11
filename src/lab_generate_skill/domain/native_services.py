"""Observed original service master exits, never descendant/resource closure."""

from typing import Literal
from lab_generate_skill.domain.validation import Contract, Identifier
from pydantic import Field, model_validator
from typing import Self


class NativeServiceExit(Contract):
    schema_version: Literal["native-service-exit/1"] = "native-service-exit/1"
    service: Identifier
    process_id: int = Field(gt=0)
    returncode: int | None
    state: Literal["reaped", "unconfirmed"]
    kill_requested: bool

    @model_validator(mode="after")
    def observed(self) -> Self:
        if (self.returncode is not None) != (self.state == "reaped"):
            raise ValueError("Reaped master requires an observed return code")
        return self
