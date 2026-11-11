"""Strict original ordinary navigation metadata to current private declarations."""

import json
from typing import Any, Literal
from pydantic import Field, JsonValue, model_validator
from typing import Self
from lab_generate_skill.domain.validation import Contract, NonEmptyText
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask
from .navigation_spec import (
    LocalGoalRevision,
    NavigationSourceBinding,
    RouteAlternative,
    RouteDisplay,
    NavigationRoute,
    NavigationCompletion,
    NavigationSpec,
    NavigationInputs,
)


class OriginalAlternative(Contract):
    profile: Literal["car", "bike", "foot"]
    native: RouteDisplay
    backend: dict[str, JsonValue]


class OriginalRoute(Contract):
    pair: tuple[tuple[float, float], tuple[float, float]]
    alternatives: tuple[OriginalAlternative, ...] = Field(min_length=1, max_length=3)
    endpoint_labels: tuple[tuple[NonEmptyText, ...], tuple[NonEmptyText, ...]]


class OriginalCompletion(Contract):
    path_regex: NonEmptyText
    heading_regex: NonEmptyText
    map_route: OriginalRoute | None = None


class OriginalNavigation(Contract):
    task_id: NonEmptyText
    source_task_id: NonEmptyText
    domain: Literal["map"]
    split: Literal["train"] = "train"
    goal: NonEmptyText
    start_path: NonEmptyText
    recorded_start_paths: tuple[NonEmptyText, ...] = Field(min_length=1)
    source_trace_ids: tuple[NonEmptyText, ...] = Field(min_length=1)
    completion: OriginalCompletion
    control_target_path: NonEmptyText
    wrong_target_path: NonEmptyText
    verify_url_only: bool
    completion_scope: NonEmptyText
    task_text_changed: bool
    heldout_quarantine: bool
    eligible_for_training: bool
    api_calls: int = Field(ge=0, le=0)
    status: NonEmptyText
    reset_policy: Literal["guarded_unchanged_or_cold"]
    admission_result: NonEmptyText
    original_goal_equivalence: NonEmptyText | None = None
    capability_proof: NonEmptyText | None = None
    goal_revision: LocalGoalRevision | None = None
    control_positive_paths: tuple[NonEmptyText, ...] | None = None
    wrong_mode_path: NonEmptyText | None = None

    @model_validator(mode="after")
    def exact_scope(self) -> Self:
        if (
            self.heldout_quarantine
            or self.task_id != self.source_task_id
            or self.start_path not in self.recorded_start_paths
        ):
            raise ValueError("Original unquarantined train source/start required")
        if self.task_text_changed != (self.goal_revision is not None):
            raise ValueError("Changed public goal requires explicit original revision")
        if any(
            getattr(self, key) is None
            for key in (
                "goal_revision",
                "capability_proof",
                "original_goal_equivalence",
                "control_positive_paths",
                "wrong_mode_path",
            )
            if key in self.model_fields_set
        ):
            raise ValueError("Declared optional original metadata cannot be null")
        if (
            "map_route" in self.completion.model_fields_set
            and self.completion.map_route is None
        ):
            raise ValueError("Declared original route cannot be null")
        return self


def bind_navigation_inputs(
    native: dict[str, Any],
    reference: EvidenceRef,
    public: PublicTask,
    binding: NavigationSourceBinding,
) -> NavigationInputs:
    binding = NavigationSourceBinding.model_validate(binding)
    original = OriginalNavigation.model_validate_json(
        json.dumps(native, allow_nan=False)
    )
    if (original.source_task_id, original.task_id, original.goal) != (
        binding.source_task_id,
        binding.runtime_task_id,
        binding.public_goal,
    ):
        raise ValueError("Original native source/runtime identity or goal changed")
    route = original.completion.map_route
    completion = NavigationCompletion(
        path_regex=original.completion.path_regex,
        heading_regex=original.completion.heading_regex,
        map_route=(
            None
            if route is None
            else NavigationRoute(
                pair=route.pair,
                endpoint_labels=route.endpoint_labels,
                alternatives=tuple(
                    RouteAlternative(
                        profile=a.profile,
                        native=a.native,
                        backend_json=json.dumps(
                            a.backend,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        ),
                    )
                    for a in route.alternatives
                ),
            )
        ),
    )
    return NavigationInputs(
        public_task=public,
        private_spec=NavigationSpec(
            task=public.identity,
            native_contract_ref=reference,
            binding=binding,
            native_goal=original.goal,
            original_start_path=original.start_path,
            completion=completion,
            goal_revision=original.goal_revision,
        ),
    )
