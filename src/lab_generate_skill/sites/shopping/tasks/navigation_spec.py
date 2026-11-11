"""Original category-navigation data, separate from current source permission."""

import re
from typing import Literal, Self
from urllib.parse import unquote, urlsplit
from pydantic import Field, model_validator
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.validation import Contract, Identifier, NonEmptyText


def local_path(value: str) -> str:
    parts = urlsplit(value)
    if (
        not value.startswith("/")
        or value.startswith("//")
        or parts.scheme
        or parts.netloc
        or any(ord(c) < 32 or c == "\\" for c in value)
    ):
        raise ValueError("Original local category path required")
    return value


class CategoryCompletion(Contract):
    path_regex: NonEmptyText = Field(max_length=2048)
    heading_regex: NonEmptyText = Field(max_length=2048)

    @model_validator(mode="after")
    def patterns(self) -> Self:
        try:
            re.compile(self.path_regex)
            re.compile(self.heading_regex, re.I)
        except re.error as error:
            raise ValueError("Original category pattern is malformed") from error
        return self


class OriginalCategoryNavigation(Contract):
    task_id: Identifier
    source_task_id: Identifier
    domain: Literal["shopping"]
    goal: NonEmptyText
    start_path: NonEmptyText
    recorded_start_paths: tuple[NonEmptyText, ...] = Field(min_length=1)
    control_target_path: NonEmptyText
    completion: CategoryCompletion
    binding_family: Literal["category"]
    heldout_quarantine: bool
    eligible_for_training: bool
    task_text_changed: bool
    status: Literal["draft_requires_two_live_controls"]
    api_calls: int = Field(ge=0, le=0)
    admission_result: NonEmptyText
    current_entry_review: NonEmptyText

    @model_validator(mode="after")
    def original_scope(self) -> Self:
        if (
            self.task_id != self.source_task_id
            or self.heldout_quarantine
            or self.eligible_for_training
            or self.task_text_changed
            or self.start_path not in self.recorded_start_paths
        ):
            raise ValueError("Exact unchanged original train category scope required")
        for path in (*self.recorded_start_paths, self.control_target_path):
            local_path(path)
        if (
            re.fullmatch(
                self.completion.path_regex,
                unquote(urlsplit(self.control_target_path).path),
            )
            is None
        ):
            raise ValueError("Original control target differs from completion path")
        return self


class CategoryNavigationSpec(Contract):
    schema_version: Literal["shopping-category-navigation/1"] = (
        "shopping-category-navigation/1"
    )
    task: TaskIdentity
    native_contract_ref: EvidenceRef
    original: OriginalCategoryNavigation

    @model_validator(mode="after")
    def selected_original(self) -> Self:
        private_state_ref(self.native_contract_ref, "shopping-native-contract/1")
        if (
            self.task.site,
            self.task.family,
            self.task.contract_version,
            self.task.split,
            self.task.task_id,
            self.task.source_task_id,
        ) != (
            "shopping",
            "page_navigation",
            1,
            "train",
            self.original.task_id,
            self.original.source_task_id,
        ) or self.native_contract_ref.media_type != "application/json":
            raise ValueError(
                "Original Shopping category task and native reference required"
            )
        return self


class CategoryNavigationInputs(Contract):
    schema_version: Literal["shopping-category-navigation-inputs/1"] = (
        "shopping-category-navigation-inputs/1"
    )
    public_task: PublicTask
    private_spec: CategoryNavigationSpec

    @model_validator(mode="after")
    def same_task(self) -> Self:
        if self.public_task.identity != self.private_spec.task:
            raise ValueError("Public/private category task identity changed")
        return self
