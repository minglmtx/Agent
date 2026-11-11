"""Explicit public start variant; no navigation or permission grant."""

from typing import Literal
from .identity import TaskIdentity

FORUM_DIRECTORY_SOURCE = "dbab57fbe44ffe3192ec"


def image_start_path(task: TaskIdentity) -> Literal["/submit", "/forums/all"]:
    task = TaskIdentity.model_validate(task)
    if (task.site, task.family, task.contract_version, task.split) != (
        "reddit",
        "native_image_submission",
        1,
        "train",
    ):
        raise ValueError("Original selected Reddit media identity required")
    return "/forums/all" if task.source_task_id == FORUM_DIRECTORY_SOURCE else "/submit"
