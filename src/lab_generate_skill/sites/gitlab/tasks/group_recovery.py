"""Concrete Group recovery facts; full original physical tree and raw evidence."""

import hashlib
from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceResult
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from lab_generate_skill.domain.native_quiescence import NativeServiceQuiescence
from lab_generate_skill.domain.native_private_json import GITLAB_GROUP_PRIVATE_JSON
from ..snapshot import GitlabSnapshot, GitlabInventory
from ..services import require_stop
from ..generation_checks import new_generation
from ..shutdown_contract import GitalyTermExit
from ..workhorse_shutdown import WorkhorseTermExit
from .group_request import task_input
from .native_snapshot import same_native_snapshot


def native_result(result: SitePrivateEvidenceResult, request: SiteTaskRequest) -> None:
    task_input(request)
    ref, context, profile = (
        result.payload_ref,
        result.context,
        GITLAB_GROUP_PRIVATE_JSON,
    )
    if (
        context.site_id,
        request.task.site,
        request.task.family,
        request.task.contract_version,
        request.task.split,
    ) != ("gitlab", "gitlab", "group_creation", 1, "train"):
        raise ValueError("Original Group native scope required")
    if (
        (ref.visibility, ref.media_type, ref.content_schema, ref.producer)
        != ("private", "application/json", profile.content_schema, profile.producer)
        or ref.uri != "cas://sha256/" + ref.sha256
        or not 0 < ref.size_bytes <= 64 * 1024 * 1024
    ):
        raise ValueError("Complete Group native capture reference required")
    if result.request_sha256 != request.digest or (
        request.operation.run_id,
        request.operation.owner_id,
        request.operation.allocation_id,
    ) != (
        context.token.owner.run_id,
        context.token.owner.owner_id,
        context.token.allocation_id,
    ):
        raise ValueError("Group native reference changed original request/allocation")


class GroupRecoverySnapshot(Contract):
    schema_version: Literal["gitlab-group-recovery/1"] = "gitlab-group-recovery/1"
    request: SiteTaskRequest
    state: GitlabSnapshot
    native_before: SitePrivateEvidenceResult

    @model_validator(mode="after")
    def original(self) -> Self:
        native_result(self.native_before, self.request)
        if (
            self.request.action != "snapshot"
            or self.native_before.context.instance.files != self.state.service.files
        ):
            raise ValueError("Original Group snapshot/native instance required")
        require_stop(
            self.state.original_stop,
            tuple(x.original for x in self.state.original_stop.namespaces),
            self.state.gitaly_term,
            self.state.workhorse_terms,
        )
        return self


class GroupObserved(Contract):
    schema_version: Literal["gitlab-group-observed/1"] = "gitlab-group-observed/1"
    request: SiteTaskRequest
    snapshot: GroupRecoverySnapshot
    native: SitePrivateEvidenceResult

    @model_validator(mode="after")
    def original(self) -> Self:
        native_result(self.native, self.request)
        if (
            self.request.action not in ("prepare", "inspect")
            or self.native.context != self.snapshot.native_before.context
        ):
            raise ValueError("Original Group prepare/inspect context required")
        same_native_snapshot(
            self.request,
            self.snapshot.request,
            self.snapshot.model_dump_json().encode(),
            self.snapshot.schema_version,
            None,
            "Group",
        )
        return self


class GroupRestored(Contract):
    schema_version: Literal["gitlab-group-restored/1"] = "gitlab-group-restored/1"
    request: SiteTaskRequest
    snapshot: GroupRecoverySnapshot
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
            or self.native.context != self.snapshot.native_before.context
        ):
            raise ValueError("Original complete Group tree restoration required")
        same_native_snapshot(
            self.request,
            self.snapshot.request,
            self.snapshot.model_dump_json().encode(),
            self.snapshot.schema_version,
            None,
            "Group",
        )
        parent = self.request.operation.parent_operation_id
        # Exact preparation parent is enforced by the stateful task adapter;
        # a persisted restore must at least retain a real linked cleanup parent.
        if parent is None:
            raise ValueError("Group restoration lost original linked cleanup parent")
        require_stop(
            self.stopped,
            tuple(x.original for x in self.stopped.namespaces),
            self.gitaly_term,
            self.workhorse_terms,
        )
        image = self.snapshot.state.service.files.image.sha256
        if (
            self.gitaly_term is not None and self.gitaly_term.image_sha256 != image
        ) or any(p.image_sha256 != image for p in self.workhorse_terms):
            raise ValueError("Group restoration changed original native implementation")
        new_generation(
            self.snapshot.state.original_stop,
            tuple(x.original for x in self.stopped.namespaces),
        )
        return self


class GroupResumed(Contract):
    schema_version: Literal["gitlab-group-resumed/1"] = "gitlab-group-resumed/1"
    request: SiteResumeRequest
    restored: GroupRestored
    native: SitePrivateEvidenceResult
    original_pins: tuple[NativeNamespaceIdentity, ...]

    @model_validator(mode="after")
    def original(self) -> Self:
        if (
            self.request.restore_request != self.restored.request
            or self.native.context != self.restored.native.context
        ):
            raise ValueError("Group resume changed original restoration/site")
        returned = (
            SiteTaskResult(
                request_sha256=self.restored.request.digest,
                private_result=self.restored.model_dump_json(),
            )
            .model_dump_json()
            .encode()
        )
        ref = self.request.restore_result_ref
        if (ref.sha256, ref.size_bytes) != (
            hashlib.sha256(returned).hexdigest(),
            len(returned),
        ):
            raise ValueError("Group resume changed original returned restore bytes")
        inspection = self.request.restore_request.model_copy(
            update={"operation": self.request.operation}
        )
        native_result(self.native, inspection)
        new_generation(self.restored.stopped, self.original_pins)
        return self
