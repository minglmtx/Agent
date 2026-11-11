"""Read canonical original Reddit preparation facts, never execute native work."""

import hashlib
from typing import TypeVar
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evaluation import CheckResult
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceResult
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from .image_state import ImageReference
from .native_schema import NativeCapture
from .tasks.image_admission import task_input
from .tasks.image_recovery import native_result

T = TypeVar("T", bound=Contract)


class RedditStateReads:
    def __init__(self, store: EvidenceReader) -> None:
        self.store = store

    def read(
        self, ref: EvidenceRef, schema: str, model: type[T], control: OperationControl
    ) -> T:
        control.checkpoint()
        private_state_ref(ref, schema)
        if ref.media_type != "application/json":
            raise ValueError("Reddit state evidence must be private JSON")
        raw = self.store.read(ref, control=control)
        if (len(raw), hashlib.sha256(raw).hexdigest()) != (ref.size_bytes, ref.sha256):
            raise EvidenceIntegrityError("Original Reddit evidence bytes changed")
        value = model.model_validate_json(raw)
        if value.model_dump_json().encode() != raw:
            raise EvidenceIntegrityError("Noncanonical original Reddit state evidence")
        control.checkpoint()
        return value

    def _native(
        self,
        descriptor: SitePrivateEvidenceResult,
        request: SiteTaskRequest,
        model: type[T],
        control: OperationControl,
    ) -> T:
        descriptor = SitePrivateEvidenceResult.model_validate(descriptor)
        native_result(descriptor, request)
        return self.read(
            descriptor.payload_ref, "reddit-native-private-json/1", model, control
        )

    def reference(
        self,
        descriptor: SitePrivateEvidenceResult,
        request: SiteTaskRequest,
        control: OperationControl,
    ) -> ImageReference:
        if request.action != "snapshot":
            raise ValueError("Original Reddit snapshot reference required")
        value = self._native(descriptor, request, ImageReference, control)
        if value.target_forum.name != task_input(request).parameters.forum:
            raise EvidenceIntegrityError(
                "Reddit reference changed original requested forum"
            )
        return value

    def capture(
        self,
        descriptor: SitePrivateEvidenceResult,
        request: SiteTaskRequest,
        control: OperationControl,
    ) -> NativeCapture:
        if request.action == "snapshot":
            raise ValueError(
                "Capture cannot substitute for the original native reference"
            )
        return self._native(descriptor, request, NativeCapture, control)

    @staticmethod
    def checks(
        names: tuple[str, ...], refs: tuple[EvidenceRef, ...], reason: str
    ) -> StateChecks:
        return StateChecks(
            required=names,
            checks=tuple(
                CheckResult(name=name, status="pass", reason_code=reason, evidence=refs)
                for name in names
            ),
        )
