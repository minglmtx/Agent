"""Private navigation declarations; original bytes remain authoritative evidence."""

import json
import math
import re
from typing import Literal, Self
from urllib.parse import urlsplit
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import (
    Contract,
    Identifier,
    NonEmptyText,
    Sha256,
)
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.domain.task import PublicTask


class HistoricalPin(Contract):
    path: NonEmptyText
    sha256: Sha256


class OrdinaryMapProfile(Contract):
    capture_mail: bool
    community: None
    editor: None
    optional: dict[str, str]
    layers: bool
    gitlab_initial: None
    gitlab_cache: None

    @model_validator(mode="after")
    def no_optional_setup(self) -> Self:
        if self.optional or self.capture_mail or self.layers:
            raise ValueError("Selected ordinary navigation has no optional setup")
        return self


class NavigationSourceBinding(Contract):
    source_task_id: Identifier
    active_task_id: Identifier
    runtime_task_id: Identifier
    domain: Literal["map"]
    public_goal: NonEmptyText
    protocol: Literal["navigation"]
    evaluator_version: Literal["site-navigation-v3"]
    profile: OrdinaryMapProfile
    admission: HistoricalPin
    original_entry: HistoricalPin
    original_contract_sha256: Sha256
    training_pointer: HistoricalPin
    retained_control_review: NonEmptyText
    registration_status: NonEmptyText
    initial_policy: Literal["retained_native_admission_plus_actual_runtime_check"]
    formal_queue_ready: bool
    native_contract: HistoricalPin


class LocalGoalRevision(Contract):
    version: Literal["explicit-local-navigation-scope-v1"]
    original_goal: NonEmptyText
    reason: NonEmptyText
    original_benchmark_equivalence: bool

    @model_validator(mode="after")
    def explicit_derived_scope(self) -> Self:
        if self.original_benchmark_equivalence:
            raise ValueError(
                "Local navigation does not assert original goal equivalence"
            )
        return self


class RouteDisplay(Contract):
    origin: str
    destination: str
    engine: str
    summary: str
    rows: tuple[str, ...]
    route_visible: bool
    loading: bool


class RouteAlternative(Contract):
    profile: Literal["car", "bike", "foot"]
    native: RouteDisplay
    backend_json: NonEmptyText

    @model_validator(mode="after")
    def complete_original_backend(self) -> Self:
        value = json.loads(self.backend_json)
        if (
            not isinstance(value, dict)
            or set(value) != {"legs", "weight_name", "weight", "duration", "distance"}
            or not isinstance(value["legs"], list)
            or not value["legs"]
            or any(not isinstance(x, dict) for x in value["legs"])
            or not isinstance(value["weight_name"], str)
            or not value["weight_name"].strip()
            or any(
                type(value[k]) not in (int, float)
                or not math.isfinite(value[k])
                or value[k] < 0
                for k in ("weight", "duration", "distance")
            )
            or json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
            != self.backend_json
        ):
            raise ValueError("Complete canonical original OSRM route object required")
        if self.native.loading or not self.native.route_visible or not self.native.rows:
            raise ValueError("Original route reference must be fully rendered")
        labels = {"car": "Car (OSRM)", "bike": "Bicycle (OSRM)", "foot": "Foot (OSRM)"}
        if self.native.engine != labels[self.profile]:
            raise ValueError("Original route reference mode and display disagree")
        return self


class NavigationRoute(Contract):
    pair: tuple[tuple[float, float], tuple[float, float]]
    alternatives: tuple[RouteAlternative, ...] = Field(min_length=1, max_length=3)
    endpoint_labels: tuple[tuple[NonEmptyText, ...], tuple[NonEmptyText, ...]]

    @model_validator(mode="after")
    def original_endpoints(self) -> Self:
        if any(
            not math.isfinite(lat)
            or not math.isfinite(lon)
            or not -90 <= lat <= 90
            or not -180 <= lon <= 180
            for lat, lon in self.pair
        ):
            raise ValueError("Finite original geographic endpoints required")
        if len({a.profile for a in self.alternatives}) != len(self.alternatives):
            raise ValueError("Duplicate original route alternative")
        if any(
            not names or len(set(names)) != len(names) for names in self.endpoint_labels
        ):
            raise ValueError("Distinct original endpoint name references required")
        return self


class NavigationCompletion(Contract):
    path_regex: NonEmptyText = Field(max_length=4096)
    heading_regex: NonEmptyText = Field(max_length=4096)
    map_route: NavigationRoute | None

    @model_validator(mode="after")
    def patterns(self) -> Self:
        try:
            re.compile(self.path_regex)
            re.compile(self.heading_regex)
        except re.error as error:
            raise ValueError("Invalid original page identity pattern") from error
        if not self.path_regex.startswith("/"):
            raise ValueError("Explicit local page path pattern required")
        return self


class NavigationSpec(Contract):
    schema_version: Literal["map-navigation-spec/1"] = "map-navigation-spec/1"
    task: TaskIdentity
    native_contract_ref: EvidenceRef
    binding: NavigationSourceBinding
    native_goal: NonEmptyText
    original_start_path: NonEmptyText
    completion: NavigationCompletion
    goal_revision: LocalGoalRevision | None
    admission: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def original_source(self) -> Self:
        t, b = self.task, self.binding
        if (t.site, t.family, t.contract_version, t.split) != (
            "map",
            "navigation_page_identity",
            1,
            "train",
        ):
            raise ValueError("Explicit original train Map navigation v1 required")
        if (t.source_task_id, t.task_id, self.native_goal) != (
            b.source_task_id,
            b.active_task_id,
            b.public_goal,
        ):
            raise ValueError("Original active/source identity or public goal changed")
        if b.runtime_task_id != b.source_task_id:
            raise ValueError("Selected original runtime/source identity changed")
        private_state_ref(self.native_contract_ref, "map-native-contract/1")
        if (
            self.native_contract_ref.media_type != "application/json"
            or self.native_contract_ref.sha256 != b.native_contract.sha256
        ):
            raise ValueError("Original bound native contract reference changed")
        derived = self.goal_revision is not None
        if derived != (b.active_task_id != b.runtime_task_id) or (
            derived and not b.active_task_id.startswith(b.source_task_id + "--derived-")
        ):
            raise ValueError("Explicit local derived task lineage required")
        u = urlsplit(self.original_start_path)
        if (
            u.scheme
            or u.netloc
            or not self.original_start_path.startswith("/")
            or self.original_start_path.startswith("//")
            or any(
                c.isspace() or ord(c) < 32 or c == "\\"
                for c in self.original_start_path
            )
        ):
            raise ValueError("Original local start path required")
        return self


class NavigationInputs(Contract):
    schema_version: Literal["map-navigation-inputs/1"] = "map-navigation-inputs/1"
    public_task: PublicTask
    private_spec: NavigationSpec

    @model_validator(mode="after")
    def same_public_view(self) -> Self:
        public, private = self.public_task, self.private_spec
        u = urlsplit(public.start_url)
        if (
            public.identity != private.task
            or public.goal != private.native_goal
            or u.scheme != "http"
            or u.hostname != "127.0.0.1"
            or u.port is None
            or not 1024 <= u.port <= 65535
            or public.start_url
            != f"http://127.0.0.1:{u.port}" + private.original_start_path
            or "send_msg_to_user" not in public.allowed_actions
        ):
            raise ValueError("Allocated original public navigation view required")
        return self
