"""Original SSH-key task, full stopped tree and complete private native refs."""

from typing import Literal, Self
from pydantic import model_validator, Field
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceResult
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from lab_generate_skill.domain.native_quiescence import NativeServiceQuiescence
from ..snapshot import GitlabSnapshot, GitlabInventory
from ..services import require_stop
from ..generation_checks import new_generation
from ..shutdown_contract import GitalyTermExit
from ..workhorse_shutdown import WorkhorseTermExit


def native_result(result: SitePrivateEvidenceResult, request: SiteTaskRequest) -> None:
    ref, context = result.payload_ref, result.context
    if (
        request.task.site,
        request.task.family,
        request.task.contract_version,
        request.task.split,
    ) != ("gitlab", "profile_ssh_key", 1, "train"):
        raise ValueError("Selected SSH-key native task required")
    if (
        (ref.visibility, ref.media_type, ref.content_schema, ref.producer)
        != (
            "private",
            "application/json",
            "gitlab-native-private-json/1",
            "fixed-gitlab-native-private-v1",
        )
        or ref.uri != "cas://sha256/" + ref.sha256
        or not 0 < ref.size_bytes <= 64 * 1024 * 1024
    ):
        raise ValueError("Complete original private GitLab native reference required")
    if result.request_sha256 != request.digest or (
        request.operation.run_id,
        request.operation.owner_id,
        request.operation.allocation_id,
    ) != (
        context.token.owner.run_id,
        context.token.owner.owner_id,
        context.token.allocation_id,
    ):
        raise ValueError("Native reference changed original request/allocation")


class SshKeyRecoverySnapshot(Contract):
    schema_version: Literal["gitlab-ssh-key-recovery/1"] = "gitlab-ssh-key-recovery/1"
    request: SiteTaskRequest
    state: GitlabSnapshot
    native_before: SitePrivateEvidenceResult

    @model_validator(mode="after")
    def original(self) -> Self:
        request, context = self.request, self.native_before.context
        native_result(self.native_before, request)
        if (
            request.action != "snapshot"
            or self.native_before.request_sha256 != request.digest
            or context.instance.files != self.state.service.files
        ):
            raise ValueError("Original SSH-key snapshot/native capture scope required")
        if (
            request.operation.run_id,
            request.operation.owner_id,
            request.operation.allocation_id,
        ) != (
            context.token.owner.run_id,
            context.token.owner.owner_id,
            context.token.allocation_id,
        ):
            raise ValueError("Snapshot changed original native resource allocation")
        require_stop(
            self.state.original_stop,
            tuple(x.original for x in self.state.original_stop.namespaces),
            self.state.gitaly_term,
            self.state.workhorse_terms,
        )
        return self


class SshKeyObserved(Contract):
    schema_version: Literal["gitlab-ssh-key-observed/1"] = "gitlab-ssh-key-observed/1"
    request: SiteTaskRequest
    snapshot: SshKeyRecoverySnapshot
    native: SitePrivateEvidenceResult

    @model_validator(mode="after")
    def original(self) -> Self:
        native_result(self.native, self.request)
        if (
            self.request.action not in ("prepare", "inspect")
            or self.native.request_sha256 != self.request.digest
            or self.request.task != self.snapshot.request.task
        ):
            raise ValueError("Original SSH-key prepare/inspect capture required")
        if self.native.context != self.snapshot.native_before.context:
            raise ValueError("Native capture changed original site context")
        return self


class SshKeyRestored(Contract):
    schema_version: Literal["gitlab-ssh-key-restored/2"] = "gitlab-ssh-key-restored/2"
    request: SiteTaskRequest
    snapshot: SshKeyRecoverySnapshot
    stopped: NativeServiceQuiescence
    inventory: GitlabInventory
    native: SitePrivateEvidenceResult
    gitaly_term: GitalyTermExit | None = None
    workhorse_terms: tuple[WorkhorseTermExit, ...] = Field(default=(), max_length=2)

    @model_validator(mode="after")
    def original(self) -> Self:
        native_result(self.native, self.request)
        if (
            self.request.action != "restore"
            or self.inventory != self.snapshot.state.inventory
            or self.native.request_sha256 != self.request.digest
        ):
            raise ValueError("Original complete SSH-key tree restoration required")
        require_stop(
            self.stopped,
            tuple(x.original for x in self.stopped.namespaces),
            self.gitaly_term,
            self.workhorse_terms,
        )
        if (
            self.gitaly_term is not None
            and self.gitaly_term.image_sha256
            != self.snapshot.state.service.files.image.sha256
        ):
            raise ValueError("Restoration changed fixed Gitaly implementation")
        if any(
            p.image_sha256 != self.snapshot.state.service.files.image.sha256
            for p in self.workhorse_terms
        ):
            raise ValueError("Restoration changed fixed Workhorse implementation")
        new_generation(
            self.snapshot.state.original_stop,
            tuple(x.original for x in self.stopped.namespaces),
        )
        if self.native.context != self.snapshot.native_before.context:
            raise ValueError("Restoration changed original site context")
        return self


class SshKeyResumed(Contract):
    schema_version: Literal["gitlab-ssh-key-resumed/1"] = "gitlab-ssh-key-resumed/1"
    request: SiteResumeRequest
    restored: SshKeyRestored
    native: SitePrivateEvidenceResult
    original_pins: tuple[NativeNamespaceIdentity, ...]

    @model_validator(mode="after")
    def original(self) -> Self:
        if (
            self.request.restore_request != self.restored.request
            or self.native.context != self.restored.native.context
        ):
            raise ValueError("Resume changed original SSH-key restoration/site")
        inspection = self.request.restore_request.model_copy(
            update={"operation": self.request.operation}
        )
        native_result(self.native, inspection)
        if self.native.request_sha256 != inspection.digest:
            raise ValueError("Resume native fact lost original read operation")
        new_generation(self.restored.stopped, self.original_pins)
        return self
