"""Private original GitLab worker/context descriptor, never task success proof."""

from typing import Literal, Self
from pydantic import model_validator
from .validation import Contract, Sha256
from .site_worker import SiteInstanceStarted
from .process_guard import ProcessOwnerGuard
from .lifecycle import AllocationToken
from .evidence import EvidenceRef


class SitePrivateEvidenceContext(Contract):
    schema_version: Literal["site-private-evidence-context/1"] = (
        "site-private-evidence-context/1"
    )
    configuration_sha256: Sha256
    site_id: Literal["gitlab", "reddit"] = "gitlab"
    token: AllocationToken
    instance: SiteInstanceStarted
    owner_guard: ProcessOwnerGuard

    @model_validator(mode="after")
    def original_site(self) -> Self:
        if (
            self.token.scope,
            self.token.resource_kind,
            self.token.expected_resource_id,
        ) != ("batch", "site", self.instance.files.instance_id):
            raise ValueError("Private facts require the original batch site instance")
        return self


class SitePrivateEvidenceResult(Contract):
    schema_version: Literal["site-private-evidence-result/1"] = (
        "site-private-evidence-result/1"
    )
    request_sha256: Sha256
    context: SitePrivateEvidenceContext
    payload_ref: EvidenceRef
