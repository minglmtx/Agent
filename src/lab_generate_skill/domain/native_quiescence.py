"""Original service and namespace exits, without a database consistency claim."""

from typing import Literal, Self
from pydantic import Field, model_validator
from .validation import Contract
from .native_services import NativeServiceExit
from .native_namespace import NativeNamespaceStopped


class NativeServiceQuiescence(Contract):
    schema_version: Literal["native-service-quiescence/1"] = (
        "native-service-quiescence/1"
    )
    masters: tuple[NativeServiceExit, ...] = Field(min_length=1, max_length=64)
    namespaces: tuple[NativeNamespaceStopped, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def original_services(self) -> Self:
        masters = {x.service: x for x in self.masters}
        names = [x.original.service for x in self.namespaces]
        if (
            len(masters) != len(self.masters)
            or len(set(names)) != len(names)
            or set(names) != set(masters)
        ):
            raise ValueError(
                "Quiescence requires every distinct original service namespace"
            )
        for stopped in self.namespaces:
            master = masters[stopped.original.service]
            if (
                master.state != "reaped"
                or master.kill_requested
                or master.process_id != stopped.original.launcher.process_id
                or master.returncode != stopped.launcher_returncode
            ):
                raise ValueError(
                    "Quiescence changed original service/exit or used forced cleanup"
                )
        return self
