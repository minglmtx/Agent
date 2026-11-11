"""Original selected native account/forum/ranges plus complete initial capture."""

from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract, NonEmptyText
from .native_schema import NativeId, NativeCapture


class NativeAccount(Contract):
    id: NativeId
    username: NonEmptyText


class NativeForum(Contract):
    id: NativeId
    name: NonEmptyText


class ImageReference(Contract):
    version: Literal["reddit-native-real-photo-candidate-v1"]
    account: NativeAccount
    target_forum: NativeForum
    existing_forum_ids: tuple[NativeId, ...] = Field(min_length=1, max_length=100000)
    known_id_ranges: tuple[tuple[NativeId, NativeId], ...] = Field(max_length=1000000)
    capture: NativeCapture

    @model_validator(mode="after")
    def pristine_native_reference(self) -> Self:
        if (
            tuple(sorted(set(self.existing_forum_ids))) != self.existing_forum_ids
            or self.target_forum.id not in self.existing_forum_ids
        ):
            raise ValueError("Original existing requested forum required")
        end = 0
        covered = 0
        for lo, hi in self.known_id_ranges:
            if not end < lo <= hi:
                raise ValueError("Ordered disjoint original native id ranges required")
            covered += hi - lo + 1
            end = hi
        c = self.capture
        if (
            covered != c.complete13.submissions.count
            or c.added_posts
            or c.attached_image is not None
            or c.all_original_submissions != c.complete13.submissions
            or c.full_original_vote_scope.excluded_only_new_post_id is not None
            or c.full_original_vote_scope.new_post_votes
            or c.auxiliary.excluded_only_new_image_id is not None
            or c.full_original_vote_scope.original
            != c.complete13.twelve_task_tables["submission_votes"]
        ):
            raise ValueError("Pristine complete original native reference required")
        return self
