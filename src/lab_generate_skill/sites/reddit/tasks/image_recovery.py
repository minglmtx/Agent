"""Small original recovery envelopes; complete native facts remain private CAS."""

from typing import Literal, Self
from pydantic import model_validator
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceResult
from lab_generate_skill.domain.reddit_native_read_input import BaselineIdsRef
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from lab_generate_skill.domain.native_quiescence import NativeServiceQuiescence
from lab_generate_skill.domain.native_private_json import REDDIT_PRIVATE_JSON
from ..media_initialization_contract import MediaInitialization
from ..snapshot import RedditSnapshot, RedditInventory
from ..services import require_stop
from ..service_commands import SERVICE_NAMES
from .image_admission import task_input, snapshot_reference


def native_result(result: SitePrivateEvidenceResult, request: SiteTaskRequest) -> None:
    task_input(request)
    ref, context = result.payload_ref, result.context
    profile = REDDIT_PRIVATE_JSON
    if (
        (ref.visibility, ref.media_type, ref.content_schema, ref.producer)
        != ("private", "application/json", profile.content_schema, profile.producer)
        or ref.uri != "cas://sha256/" + ref.sha256
        or not 0 < ref.size_bytes <= 64 * 1024**2
        or result.request_sha256 != request.digest
        or (
            request.operation.run_id,
            request.operation.owner_id,
            request.operation.allocation_id,
        )
        != (
            context.token.owner.run_id,
            context.token.owner.owner_id,
            context.token.allocation_id,
        )
        or context.site_id != "reddit"
    ):
        raise ValueError("Original complete private Reddit native evidence required")


def new_generation(
    old: NativeServiceQuiescence, pins: tuple[NativeNamespaceIdentity, ...]
) -> None:
    prior = {p.original.service: p.original for p in old.namespaces}
    if tuple(p.service for p in pins) != SERVICE_NAMES or set(prior) != set(
        SERVICE_NAMES
    ):
        raise ValueError("All three original Reddit service namespaces required")
    for pin in pins:
        previous = prior[pin.service]
        for before, after in (
            (previous.launcher, pin.launcher),
            (previous.init, pin.init),
        ):
            if (
                before == after
                or (before.node_id, before.boot_id) != (after.node_id, after.boot_id)
                or after.start_ticks < before.start_ticks
            ):
                raise ValueError(
                    "Reddit generation reused a closed process or changed host/boot/order"
                )


class ImageRecoverySnapshot(Contract):
    schema_version: Literal["reddit-image-recovery/2"] = "reddit-image-recovery/2"
    request: SiteTaskRequest
    state: RedditSnapshot
    native_before: SitePrivateEvidenceResult
    media_initialization: MediaInitialization
    baseline_ids: BaselineIdsRef

    @model_validator(mode="after")
    def original(self) -> Self:
        native_result(self.native_before, self.request)
        if (
            self.media_initialization.service != self.state.service
            or self.request.action != "snapshot"
            or self.native_before.context.instance.files != self.state.service.files
            or self.baseline_ids.task != self.request.task
            or self.baseline_ids.request_sha256 != self.request.digest
        ):
            raise ValueError(
                "Original Reddit snapshot and immutable baseline IDs required"
            )
        return self

    def check_request(self, request: SiteTaskRequest) -> None:
        snapshot_reference(
            request,
            self.request,
            self.model_dump_json().encode(),
            self.schema_version,
            None,
        )


class ImageObserved(Contract):
    schema_version: Literal["reddit-image-observed/1"] = "reddit-image-observed/1"
    request: SiteTaskRequest
    snapshot: ImageRecoverySnapshot
    native: SitePrivateEvidenceResult

    @model_validator(mode="after")
    def original(self) -> Self:
        self.snapshot.check_request(self.request)
        native_result(self.native, self.request)
        if (
            self.request.action not in ("prepare", "inspect")
            or self.native.context != self.snapshot.native_before.context
        ):
            raise ValueError(
                "Original Reddit prepare/inspect and site context required"
            )
        return self


class ImageRestored(Contract):
    schema_version: Literal["reddit-image-restored/1"] = "reddit-image-restored/1"
    request: SiteTaskRequest
    snapshot: ImageRecoverySnapshot
    stopped: NativeServiceQuiescence
    inventory: RedditInventory

    @model_validator(mode="after")
    def original(self) -> Self:
        self.snapshot.check_request(self.request)
        require_stop(self.stopped, tuple(x.original for x in self.stopped.namespaces))
        new_generation(
            self.snapshot.state.original_stop,
            tuple(x.original for x in self.stopped.namespaces),
        )
        if (
            self.request.action != "restore"
            or self.inventory != self.snapshot.state.inventory
        ):
            raise ValueError(
                "Original complete stopped Reddit tree restoration required"
            )
        return self


class ImageResumed(Contract):
    schema_version: Literal["reddit-image-resumed/1"] = "reddit-image-resumed/1"
    request: SiteResumeRequest
    restored: ImageRestored
    native: SitePrivateEvidenceResult
    original_pins: tuple[NativeNamespaceIdentity, ...]

    @model_validator(mode="after")
    def original(self) -> Self:
        if (
            self.request.restore_request != self.restored.request
            or self.native.context != self.restored.snapshot.native_before.context
        ):
            raise ValueError("Resume changed original Reddit restoration/site")
        inspection = self.request.restore_request.model_copy(
            update={"operation": self.request.operation}
        )
        native_result(self.native, inspection)
        new_generation(self.restored.stopped, self.original_pins)
        return self
