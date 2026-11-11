"""Public navigation only; no private credentials or site-specific imports."""

from typing import Any
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.ports.lifecycle import OperationControl


class NavigatePublicTask:
    def setup(self, page: Any, task: PublicTask, control: OperationControl) -> None:
        remaining = control.checkpoint()
        page.goto(task.start_url, timeout=min(10000, remaining * 1000))
        control.checkpoint()
