"""Model-visible read proposal; original private scope is bound by the consumer."""

from typing import Annotated, Literal
from pydantic import Field, field_validator
from .observation_read import ObservationRegionRange
from .validation import Contract, Identifier, Sha256


class ObservationReadChoice(Contract):
    schema_version: Literal["observation-read-choice/1"] = "observation-read-choice/1"
    snapshot_sha256: Sha256
    output_tokens: int = Field(ge=1, le=61440)
    continuation: Identifier | None = None


class ListObservationChoice(ObservationReadChoice):
    tool: Literal["list_regions"] = "list_regions"
    parent_region_id: Identifier | None = None


class ReadObservationChoice(ObservationReadChoice):
    tool: Literal["read_region"] = "read_region"
    ranges: tuple[ObservationRegionRange, ...] = Field(min_length=1, max_length=16)


class SearchObservationChoice(ObservationReadChoice):
    tool: Literal["search_regions"] = "search_regions"
    query: str = Field(min_length=1, max_length=256)
    mode: Literal["unicode_casefold_literal/1"] = "unicode_casefold_literal/1"
    region_ids: tuple[Identifier, ...] = Field(max_length=128)

    @field_validator("query")
    @classmethod
    def query_utf8(cls, value: str) -> str:
        value.encode("utf-8")
        return value


ActorObservationReadChoice = Annotated[
    ListObservationChoice | ReadObservationChoice | SearchObservationChoice,
    Field(discriminator="tool"),
]
