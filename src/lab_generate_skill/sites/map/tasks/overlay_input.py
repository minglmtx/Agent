"""Exact selected legacy declaration; never imports or invokes its old runner."""

from typing import Any, Literal
from urllib.parse import urlsplit
from pydantic import Field
from lab_generate_skill.domain.validation import Contract, NonEmptyText
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask
from .overlay_spec import GOAL, SOURCE, START, NativeOverlayInputs, NativeOverlaySpec


class OriginalCompletion(Contract):
    version: Literal["map-original-local-layer-transition-v1"]
    kind: Literal["native_map_data"]
    original_goal: str
    allowed_local_overlay_labels: list[Literal["Map Data"]] = Field(
        min_length=1, max_length=1
    )
    no_private_positive_steps_in_public_goal: bool
    normal_admitted: bool
    preserve_original_area: bool
    retain_original_native_route: bool
    semantic_review_required: bool


class OriginalTransport(Contract):
    version: Literal["map-native-layer-normal-runtime-v1"]
    native_batch_seconds: int = Field(ge=300, le=300)


class OriginalOverlay(Contract):
    admission_result: NonEmptyText
    completion: OriginalCompletion
    domain: Literal["map"]
    eligible_for_training: bool
    goal: str
    heldout_quarantine: bool
    map_native_layer: OriginalTransport
    recorded_start_paths: list[str] = Field(min_length=1, max_length=1)
    recorded_start_urls: list[NonEmptyText] = Field(min_length=1, max_length=1)
    source_aliases: list[Literal["b9101b71aacd51b61f6e"]] = Field(
        min_length=1, max_length=1
    )
    source_task_id: Literal["b9101b71aacd51b61f6e"]
    source_trace_ids: list[NonEmptyText] = Field(min_length=2, max_length=2)
    start_path: str
    task_id: Literal["b9101b71aacd51b61f6e"]


def bind_overlay_inputs(
    native: dict[str, Any], reference: EvidenceRef, public: PublicTask
) -> NativeOverlayInputs:
    original = OriginalOverlay.model_validate(native)
    scope = original.completion
    if (
        original.goal != GOAL
        or scope.original_goal != GOAL
        or original.start_path != START
        or original.recorded_start_paths != [START]
        or original.eligible_for_training
        or original.heldout_quarantine
        or not scope.no_private_positive_steps_in_public_goal
        or scope.normal_admitted
        or scope.preserve_original_area
        or not scope.retain_original_native_route
        or not scope.semantic_review_required
        or original.source_trace_ids != ["gobrowse:2346", "gobrowse:2353"]
    ):
        raise ValueError("Original unadmitted route/MapData scope or lineage changed")
    for value in original.recorded_start_urls:
        u = urlsplit(value)
        suffix = (
            u.path
            + ("?" + u.query if u.query else "")
            + ("#" + u.fragment if u.fragment else "")
        )
        if (
            u.scheme != "http"
            or not u.hostname
            or u.username is not None
            or u.password is not None
            or suffix != START
            or any(c.isspace() or ord(c) < 32 or c == "\\" for c in value)
        ):
            raise ValueError("Original recorded route URL required")
    return NativeOverlayInputs(
        public_task=public,
        private_spec=NativeOverlaySpec(
            task=public.identity, native_contract_ref=reference
        ),
    )
