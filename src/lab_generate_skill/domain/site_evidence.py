"""Predeclared private site CAS, outside mutable state; no storage admission."""

from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import Field, field_validator, model_validator
from .validation import Contract
from .evidence_storage import EvidenceStorageConfig
from .evidence_sessions import EvidenceSessionBinding
from .site_files import SiteFilesPlan
from .lifecycle import AllocationToken
from .release_installation import ReleaseInstallation
from .errors import OwnershipConflict
from .native_private_json import NativePrivateJsonProfile


class SitePrivateEvidencePlan(Contract):
    schema_version: Literal["site-private-evidence-plan/3"] = (
        "site-private-evidence-plan/3"
    )
    profile: NativePrivateJsonProfile
    binding: EvidenceSessionBinding
    config: EvidenceStorageConfig
    resource_journal_root: str = Field(min_length=1, max_length=4096)

    @field_validator("resource_journal_root")
    @classmethod
    def original_journal(cls, value: str) -> str:
        return SiteFilesPlan.canonical(value)

    @model_validator(mode="after")
    def original_storage(self) -> Self:
        binding, config = self.binding, self.config
        if binding.scope != "run" or binding.source_task_id is not None:
            raise ValueError(
                "Site private artifacts use explicit run storage, without source claims"
            )
        if (binding.storage_id, binding.storage_config_sha256, binding.release_id) != (
            config.storage_id,
            config.sha256,
            config.installation.manifest.release_id,
        ):
            raise ValueError(
                "Private site storage differs from its frozen configuration"
            )
        return self

    def check_site(
        self,
        token: AllocationToken,
        files: SiteFilesPlan,
        installation: ReleaseInstallation,
    ) -> None:
        if (
            token.scope != "batch"
            or token.resource_kind != "site"
            or token.expected_resource_id != files.instance_id
            or self.binding.owner != token.owner
            or self.config.installation != installation
        ):
            raise OwnershipConflict(
                "Private evidence changed original site owner or installation"
            )
        workspace, node = PurePosixPath(files.workspace_root), PurePosixPath(
            files.node_root
        )
        roots = (
            self.config.evidence_root,
            self.config.session_root,
            self.resource_journal_root,
        )
        for value in roots:
            root = PurePosixPath(value)
            if (
                root == workspace
                or not root.is_relative_to(workspace)
                or root.is_relative_to(node)
                or node.is_relative_to(root)
            ):
                raise OwnershipConflict(
                    "Private site evidence must outlive mutable node state in the declared workspace"
                )
        journal = PurePosixPath(self.resource_journal_root)
        for value in (self.config.evidence_root, self.config.session_root):
            other = PurePosixPath(value)
            if journal.is_relative_to(other) or other.is_relative_to(journal):
                raise OwnershipConflict(
                    "Original site journal must remain separate from private CAS/session roots"
                )
