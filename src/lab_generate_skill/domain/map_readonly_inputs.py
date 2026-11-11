"""A projection of one original closed site's readonly images/routing only.

The descriptor is not permission. The parent checks its original source owner,
and the worker checks complete declared bytes before using these exact paths.
"""

from .validation import Contract, Identifier, Sha256
from .site_files import SiteFilesPlan
from pydantic import field_validator
from pathlib import PurePosixPath


class MapReadonlyInputs(Contract):
    source_instance_id: Identifier
    source_node_root: str
    source_runtime_sha256: Sha256

    @field_validator("source_node_root")
    @classmethod
    def private_node(cls, value: str) -> str:
        value = SiteFilesPlan.canonical(value)
        if value == "/tmp" or not PurePosixPath(value).is_relative_to("/tmp"):
            raise ValueError("Original private node input root required")
        return value
