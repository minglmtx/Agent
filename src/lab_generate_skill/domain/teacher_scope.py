"""Task-level Teacher context identity, independent of all Actor attempts."""

from typing import Literal
from .validation import Contract, Identifier
from .lifecycle import ResourceOwner
from .identity import TaskIdentity


class TeacherContextScope(Contract):
    schema_version: Literal["teacher-context-scope/1"] = "teacher-context-scope/1"
    owner: ResourceOwner
    task: TaskIdentity
    context_id: Identifier
