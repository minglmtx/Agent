"""Public same-snapshot coordinates and read facts, separate from website actions."""

from typing import Annotated, Literal, Self
from pydantic import (
    Field,
    field_validator,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from typing import Any
from .actor_versions import actor_version_fields, actor_version_output
from .observation import BrowserTab
from .browser import observation_reference
from .evidence import EvidenceRef
from .state_scope import StateScope, private_state_ref
from .validation import Contract, Identifier, Sha256


class PublicObservationSnapshot(Contract):
    schema_version: Literal["public-observation-snapshot/1"] = (
        "public-observation-snapshot/1"
    )
    observation_ref: EvidenceRef
    observation_version: Literal["observation/1"] = "observation/1"
    scope: StateScope
    sequence: int = Field(ge=0)
    tab_id: Identifier
    frame_id: Identifier | None
    text_sha256: Sha256
    structure: Literal["browsergym_tab_ax/1", "opaque_public_text/1"] = (
        "browsergym_tab_ax/1"
    )
    policy_sha256: Sha256

    @model_validator(mode="after")
    def public_original(self) -> Self:
        observation_reference(self.observation_ref)
        return self


class ObservationSourceSpan(Contract):
    """Half-open Unicode codepoint coordinates in the original resolved text."""

    unit: Literal["unicode_codepoints"] = "unicode_codepoints"
    start: int = Field(ge=0)
    end: int = Field(ge=1)

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if self.start >= self.end:
            raise ValueError("Nonempty original half-open source range required")
        return self


class ObservationRegion(Contract):
    region_id: Identifier
    kind: Literal["ax_subtree", "table", "table_row", "code", "comment"]
    span: ObservationSourceSpan
    opening_span: ObservationSourceSpan
    parent_region_id: Identifier | None
    context_spans: tuple[ObservationSourceSpan, ...] = Field(max_length=512)
    data_row_spans: tuple[ObservationSourceSpan, ...] = Field(max_length=10000)
    header_spans: tuple[ObservationSourceSpan, ...] = Field(max_length=128)
    original_node_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def bounded_original_ranges(self) -> Self:
        if (
            not self.span.start
            <= self.opening_span.start
            < self.opening_span.end
            <= self.span.end
        ):
            raise ValueError("Region opening left its original subtree")
        for span in (*self.header_spans, *self.data_row_spans):
            if not self.span.start <= span.start < span.end <= self.span.end:
                raise ValueError("Table row/header left its original table")
        if self.kind != "table" and (self.header_spans or self.data_row_spans):
            raise ValueError("Only a table declares row/header ranges")
        return self


class ObservationRegionRange(Contract):
    region_id: Identifier
    unit: Literal["whole_region", "data_rows", "codepoints"]
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def explicit_coordinates(self) -> Self:
        if self.unit == "whole_region":
            if self.start is not None or self.end is not None:
                raise ValueError("Whole region cannot contain hidden slicing")
        elif self.start is None or self.end is None or self.start >= self.end:
            raise ValueError("Explicit nonempty half-open range required")
        return self


class ObservationReadBase(Contract):
    schema_version: Literal["observation-read-request/1"] = "observation-read-request/1"
    request_id: Identifier
    snapshot: PublicObservationSnapshot
    output_tokens: int = Field(ge=1, le=61440)
    continuation: Identifier | None = None


class ListObservationRegions(ObservationReadBase):
    tool: Literal["list_regions"] = "list_regions"
    parent_region_id: Identifier | None = None


class ReadObservationRegions(ObservationReadBase):
    tool: Literal["read_region"] = "read_region"
    ranges: tuple[ObservationRegionRange, ...] = Field(min_length=1, max_length=16)


class SearchObservationRegions(ObservationReadBase):
    tool: Literal["search_regions"] = "search_regions"
    query: str = Field(min_length=1, max_length=256)
    mode: Literal["unicode_casefold_literal/1"] = "unicode_casefold_literal/1"
    region_ids: tuple[Identifier, ...] = Field(max_length=128)

    @field_validator("query")
    @classmethod
    def query_utf8(cls, value: str) -> str:
        value.encode("utf-8")
        return value

    @model_validator(mode="after")
    def explicit_search_scope(self) -> Self:
        if len(set(self.region_ids)) != len(self.region_ids):
            raise ValueError("Search regions must be unique")
        return self


ObservationReadRequest = Annotated[
    ListObservationRegions | ReadObservationRegions | SearchObservationRegions,
    Field(discriminator="tool"),
]


class ObservationReadFragment(Contract):
    span: ObservationSourceSpan
    purpose: Literal[
        "content", "ancestor", "table_header", "row_identity", "current_state"
    ]
    text: str

    @model_validator(mode="after")
    def complete_fragment_length(self) -> Self:
        if len(self.text) != self.span.end - self.span.start:
            raise ValueError("Fragment differs from declared codepoint range")
        self.text.encode("utf-8")
        return self


class ObservationDirectoryEntry(Contract):
    region: ObservationRegion
    label_span: ObservationSourceSpan
    label_excerpt: str = Field(max_length=512)
    label_complete: bool

    @model_validator(mode="after")
    def explicit_excerpt(self) -> Self:
        opening = self.region.opening_span
        if (
            not opening.start
            <= self.label_span.start
            < self.label_span.end
            <= opening.end
        ):
            raise ValueError("Directory label left original opening line")
        if len(self.label_excerpt) != self.label_span.end - self.label_span.start:
            raise ValueError("Directory excerpt lost its actual source coordinate")
        if self.label_complete != (self.label_span == opening):
            raise ValueError(
                "Partial directory label cannot claim complete source text"
            )
        return self


class ObservationSearchMatch(Contract):
    match_span: ObservationSourceSpan
    region_id: Identifier


class ObservationOverview(Contract):
    """Exact already-public current tab/error facts, counted inside local body."""

    state: Literal["ready"] = "ready"
    active_tab_id: Identifier
    tabs: tuple[BrowserTab, ...] = Field(min_length=1, max_length=128)
    last_action_error: str = Field(max_length=65536)

    @model_validator(mode="after")
    def original_current_tab(self) -> Self:
        if len({tab.tab_id for tab in self.tabs}) != len(
            self.tabs
        ) or self.active_tab_id not in {tab.tab_id for tab in self.tabs}:
            raise ValueError(
                "Public overview requires unique original tabs and actual active tab"
            )
        return self


class ObservationReadPayload(Contract):
    schema_version: Literal[
        "observation-read-result/1", "observation-read-result/2"
    ] = "observation-read-result/1"
    request: ObservationReadRequest
    fragments: tuple[ObservationReadFragment, ...] = Field(max_length=2048)
    covered_ranges: tuple[ObservationSourceSpan, ...] = Field(max_length=1024)
    complete: bool
    search_coverage_complete: bool | None
    results_exhausted: bool
    omissions: tuple[Identifier, ...] = Field(max_length=64)
    continuation: Identifier | None
    directory: tuple[ObservationDirectoryEntry, ...] = Field(default=(), max_length=128)
    matches: tuple[ObservationSearchMatch, ...] = Field(default=(), max_length=128)
    overview: ObservationOverview | None = None

    @model_serializer(mode="wrap")
    def original_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return actor_version_output(
            self,
            handler,
            self.schema_version == "observation-read-result/1",
            ("overview",),
        )

    @model_validator(mode="after")
    def honest_partial_result(self) -> Self:
        old = self.schema_version == "observation-read-result/1"
        actor_version_fields(
            self, old, ("overview",), record_name="Observation read result"
        )
        if old != (self.overview is None):
            raise ValueError("Original overview requires explicit read result v2")
        if (
            self.overview is not None
            and self.overview.active_tab_id != self.request.snapshot.tab_id
        ):
            raise ValueError("Returned overview changed original captured tab")
        if self.directory and not isinstance(self.request, ListObservationRegions):
            raise ValueError(
                "Only an actual directory request returns directory entries"
            )
        if self.matches and not isinstance(self.request, SearchObservationRegions):
            raise ValueError(
                "Only an actual search request returns literal match facts"
            )
        if len({entry.region.region_id for entry in self.directory}) != len(
            self.directory
        ):
            raise ValueError("A directory page cannot repeat an original region")
        if not self.complete and not self.omissions:
            raise ValueError("Partial read requires explicit omissions")
        if self.continuation is not None and self.results_exhausted:
            raise ValueError("Exhausted result cannot promise another result page")
        if isinstance(self.request, SearchObservationRegions) != (
            self.search_coverage_complete is not None
        ):
            raise ValueError("Only search declares actual search coverage completion")
        if len(self.model_dump_json().encode()) > 1024 * 1024:
            raise ValueError("Read result exceeds original bounded evidence envelope")
        return self


class ObservationReadingDelivery(Contract):
    region: Identifier
    range: ObservationSourceSpan
    snapshot: PublicObservationSnapshot
    delivery: Literal["returned", "included_in_model_input"]
    content_ref: EvidenceRef
    model_input_ref: EvidenceRef | None

    @model_validator(mode="after")
    def delivery_is_not_understanding(self) -> Self:
        if (
            self.content_ref.visibility != "public"
            or self.content_ref.content_schema
            not in ("observation-read-result/1", "observation-read-result/2")
        ):
            raise ValueError("Original public read result required")
        if self.delivery == "included_in_model_input":
            if self.model_input_ref is None:
                raise ValueError("Actual delivery requires exact model input reference")
            private_state_ref(self.model_input_ref, "actor-model-input/1")
        elif self.model_input_ref is not None:
            raise ValueError("A returned-only record cannot claim model delivery")
        return self
