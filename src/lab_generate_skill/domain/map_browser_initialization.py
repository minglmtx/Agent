"""Explicit selected Map setup with original private preparation/site references."""

from typing import Literal, Self
from urllib.parse import urlsplit
from pydantic import Field, model_validator
from .validation import Contract
from .evidence import EvidenceRef
from .state_scope import private_state_ref
from .browser_session import BrowserSessionSpec
from .task import PublicTask


class MapNativeInitialization(Contract):
    kind: Literal["map_native_overlay"] = "map_native_overlay"
    endpoint: str = Field(min_length=1, max_length=4096)
    prepared_ref: EvidenceRef
    site_ref: EvidenceRef

    @model_validator(mode="after")
    def original_inputs(self) -> Self:
        original_map_initial_inputs(self.endpoint, self.prepared_ref, self.site_ref)
        return self

    def check(self, spec: BrowserSessionSpec) -> None:
        self.check_task(spec.task)

    def check_task(self, task: PublicTask) -> None:
        i = task.identity
        if (
            i.site,
            i.family,
            i.contract_version,
            i.split,
            i.source_task_id,
            i.task_id,
        ) != (
            "map",
            "native_route_map_data",
            1,
            "train",
            "b9101b71aacd51b61f6e",
            "b9101b71aacd51b61f6e",
        ):
            raise ValueError(
                "Only selected original train MapData initialization supported"
            )
        expected, actual = urlsplit(self.endpoint), urlsplit(task.start_url)
        if (actual.scheme, actual.netloc) != (
            expected.scheme,
            expected.netloc,
        ) or actual.path != "/directions":
            raise ValueError(
                "Selected Map task must retain its original instance/directions"
            )


def original_map_initial_inputs(
    endpoint: str, prepared_ref: EvidenceRef, site_ref: EvidenceRef
) -> None:
    u = urlsplit(endpoint)
    if (
        u.scheme != "http"
        or u.hostname != "127.0.0.1"
        or u.port is None
        or not 1024 <= u.port <= 65535
        or endpoint != f"http://127.0.0.1:{u.port}/"
    ):
        raise ValueError("Original private Map root endpoint required")
    for ref, schema in (
        (prepared_ref, "prepared-task/1"),
        (site_ref, "site-resource-started/1"),
    ):
        private_state_ref(ref, schema)
        if ref.media_type != "application/json":
            raise ValueError(
                "Original private Map JSON preparation/site references required"
            )
