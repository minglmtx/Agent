"""Explicit Actor text-view selection; no execution or task admission rights."""

from typing import Annotated, Literal
from pydantic import Field, TypeAdapter, field_validator, model_validator
from typing import Self
from .identity import Site, Split
from .observation_read_policy import ObservationReadPolicy
from .validation import Identifier
from .validation import Contract
from .identity import TaskIdentity
from .errors import OwnershipConflict


class FullAxProjection(Contract):
    schema_version: Literal["actor-full-ax-projection/1"] = "actor-full-ax-projection/1"


class MapRailsTaskScope(Contract):
    """Unchanged selected public source, shared by explicit view versions."""

    # Reserve the original first serialization slot before version subclasses.
    schema_version: str
    site: Literal["map"] = "map"
    family: Literal["native_route_map_data"] = "native_route_map_data"
    contract_version: Literal[1] = 1
    split: Literal["train"] = "train"
    source_task_id: Literal["b9101b71aacd51b61f6e"] = "b9101b71aacd51b61f6e"

    @field_validator("contract_version", mode="before")
    @classmethod
    def exact_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Exact integer contract version required")
        return value


class MapRailsDiagnosticProjection(MapRailsTaskScope):
    schema_version: Literal["actor-map-rails-diagnostic-projection/1"] = (
        "actor-map-rails-diagnostic-projection/1"
    )


class MapRailsAddressableProjection(MapRailsTaskScope):
    """Keep every original target ID, including empty structural nodes."""

    schema_version: Literal["actor-map-rails-diagnostic-projection/2"] = (
        "actor-map-rails-diagnostic-projection/2"
    )


class ObservationTaskBinding(Contract):
    site: Site
    family: Identifier
    contract_version: int = Field(ge=1)
    split: Split

    def matches(self, task: TaskIdentity) -> bool:
        return (self.site, self.family, self.contract_version, self.split) == (
            task.site,
            task.family,
            task.contract_version,
            task.split,
        )


class AdaptiveObservationProjection(Contract):
    schema_version: Literal["actor-adaptive-observation-projection/1"] = (
        "actor-adaptive-observation-projection/1"
    )
    read_policy: ObservationReadPolicy
    local_bindings: tuple[ObservationTaskBinding, ...] = Field(
        min_length=1, max_length=512
    )

    @model_validator(mode="after")
    def explicit_capability_scope(self) -> Self:
        if len(
            set(
                (b.site, b.family, b.contract_version, b.split)
                for b in self.local_bindings
            )
        ) != len(self.local_bindings):
            raise ValueError("Unique exact local capability bindings required")
        return self

    def supports_local(self, task: TaskIdentity) -> bool:
        return any(binding.matches(task) for binding in self.local_bindings)


ActorProjectionConfiguration = Annotated[
    FullAxProjection
    | MapRailsDiagnosticProjection
    | MapRailsAddressableProjection
    | AdaptiveObservationProjection,
    Field(discriminator="schema_version"),
]
_adapter: TypeAdapter[ActorProjectionConfiguration] = TypeAdapter(
    ActorProjectionConfiguration
)


def actor_projection_configuration(value: object) -> ActorProjectionConfiguration:
    return _adapter.validate_python(value)


def check_projection_task(
    configuration: ActorProjectionConfiguration, task: TaskIdentity
) -> None:
    if isinstance(configuration, MapRailsTaskScope) and (
        task.site,
        task.family,
        task.contract_version,
        task.split,
        task.source_task_id,
        task.task_id,
    ) != (
        configuration.site,
        configuration.family,
        configuration.contract_version,
        configuration.split,
        configuration.source_task_id,
        configuration.source_task_id,
    ):
        raise OwnershipConflict(
            "Diagnostic Actor view changed explicitly selected Map task"
        )
