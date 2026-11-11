"""Process identity and observed direct-child termination, never tree authority."""

from dataclasses import dataclass
from typing import Literal
from pydantic import Field
from .validation import Contract, Identifier


class ProcessIdentity(Contract):
    schema_version: Literal["process-identity/1"] = "process-identity/1"
    node_id: Identifier
    boot_id: Identifier
    process_id: int = Field(ge=1)
    start_ticks: int = Field(ge=1)


@dataclass(frozen=True)
class ProcessTermination:
    process_id: int | None
    state: Literal["not_started", "reaped", "unconfirmed"]
    returncode: int | None
    kill_requested: bool
    cleanup_errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.kill_requested) is not bool
            or type(self.cleanup_errors) is not tuple
            or any(type(x) is not str or not x for x in self.cleanup_errors)
        ):
            raise ValueError("Invalid process cleanup facts")
        if self.state == "not_started":
            if (
                self.process_id is not None
                or self.returncode is not None
                or self.kill_requested
                or self.cleanup_errors
            ):
                raise ValueError("Unstarted command cannot claim process cleanup")
        elif self.state in ("reaped", "unconfirmed"):
            if type(self.process_id) is not int or self.process_id <= 0:
                raise ValueError("Started command needs its exact positive child PID")
            if self.state == "reaped" and type(self.returncode) is not int:
                raise ValueError("Reaped child needs its observed exit status")
            if self.state == "unconfirmed" and self.returncode is not None:
                raise ValueError("Unconfirmed termination cannot invent exit status")
        else:
            raise ValueError("Unknown process termination state")
