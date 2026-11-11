"""Selected original route/MapData meaning, kept separate from public input."""

from typing import Literal, Self
from urllib.parse import urlsplit
from pydantic import model_validator
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask

SOURCE = "b9101b71aacd51b61f6e"
GOAL = "Enable the Map Data overlay to see detailed map information along the route from Central Park to Times Square."
START = "/directions?engine=fossgis_osrm_car&route=40.7830%2C-73.9650%3B40.7570%2C-73.9860#map=15/40.7695/-73.9738"


class NativeOverlaySpec(Contract):
    schema_version: Literal["map-native-overlay/1"] = "map-native-overlay/1"
    task: TaskIdentity
    native_contract_ref: EvidenceRef
    native_goal: str = GOAL
    original_start_path: str = START
    original_runtime_version: Literal["map-native-layer-normal-runtime-v1"] = (
        "map-native-layer-normal-runtime-v1"
    )
    admission: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def selected(self) -> Self:
        if (
            self.task.source_task_id,
            self.task.task_id,
            self.task.site,
            self.task.family,
            self.task.contract_version,
            self.task.split,
        ) != (SOURCE, SOURCE, "map", "native_route_map_data", 1, "train"):
            raise ValueError("Selected original train route/MapData identity required")
        if self.native_goal != GOAL or self.original_start_path != START:
            raise ValueError("Original public goal and native route required")
        ref = self.native_contract_ref
        if (ref.visibility, ref.media_type, ref.content_schema) != (
            "private",
            "application/json",
            "map-native-contract/1",
        ):
            raise ValueError("Private original Map contract required")
        return self


class NativeOverlayInputs(Contract):
    schema_version: Literal["map-native-overlay-inputs/1"] = (
        "map-native-overlay-inputs/1"
    )
    public_task: PublicTask
    private_spec: NativeOverlaySpec

    @model_validator(mode="after")
    def same_meaning(self) -> Self:
        public = self.public_task
        u = urlsplit(public.start_url)
        suffix = (
            u.path
            + ("?" + u.query if u.query else "")
            + ("#" + u.fragment if u.fragment else "")
        )
        if (
            public.identity != self.private_spec.task
            or public.goal != GOAL
            or suffix != START
            or u.scheme != "http"
            or u.hostname != "127.0.0.1"
            or u.port is None
            or not 1024 <= u.port <= 65535
            or u.username is not None
            or u.password is not None
            or "\\" in public.start_url
            or "send_msg_to_user" not in public.allowed_actions
        ):
            raise ValueError(
                "Allocated original route, public goal and completion interface required"
            )
        return self
