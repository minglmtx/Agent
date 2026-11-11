"""Task identity, independent of website processes and execution attempts.

source_task_id preserves benchmark lineage; task_id identifies the local task.
A task's split is immutable metadata, never inferred from its directory name.
"""

from typing import Literal

from pydantic import Field

from .validation import Contract, Identifier

Split = Literal["train", "dev", "test"]
Site = Literal["shopping_admin", "shopping", "gitlab", "reddit", "map"]


class TaskIdentity(Contract):
    """Input/output identity shared by task adapters, evaluators and exporters."""

    schema_version: Literal["task-identity/1"] = "task-identity/1"
    source_task_id: Identifier
    task_id: Identifier
    split: Split
    site: Site
    family: Identifier
    contract_version: int = Field(ge=1)
