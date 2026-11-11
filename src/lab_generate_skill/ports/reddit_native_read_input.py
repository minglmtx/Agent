"""Declared complete private ranges to the original native read process only."""

from typing import Protocol
from lab_generate_skill.domain.reddit_native_read_input import BaselineIdsRef
from lab_generate_skill.domain.site_task import SiteTaskRequest
from .lifecycle import OperationControl


class RedditNativeReadInputs(Protocol):
    def publish(
        self,
        request: SiteTaskRequest,
        ranges: tuple[tuple[int, int], ...],
        count: int,
        control: OperationControl,
    ) -> BaselineIdsRef: ...
    def verify(self, reference: BaselineIdsRef, control: OperationControl) -> None: ...
