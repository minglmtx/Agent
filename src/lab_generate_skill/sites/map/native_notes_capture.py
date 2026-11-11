"""Selected MapData consumer's original Notes-response capture failure guard.

Retains only actual same-origin GET/xhr Notes responses. No new request, action,
Observation, Notes task admission or semantic judgment. Body reads occur outside
callbacks under the original worker supervision, with no unknown-read retry.
"""

import hashlib
import json
import os
import threading
import traceback
from typing import Any
from urllib.parse import urlsplit
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    InvalidTransition,
    OwnershipConflict,
)
from lab_generate_skill.domain.map_private_artifact import (
    MapPrivateArtifactPlan,
    MapArtifactPlan,
)
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.map_private_artifact import MapArtifactSink
from .native_http import NativeMapHttpClient


class NativeNotesCapture:
    def __init__(
        self,
        plan: MapArtifactPlan,
        sink: MapArtifactSink,
        evidence_control: OperationControl,
        origin: str,
    ) -> None:
        self.plan = MapPrivateArtifactPlan.model_validate(plan)
        if self.plan.producer != "browser_process":
            raise ValueError("Original browser process artifact plan required")
        self.sink, self.evidence_control = sink, evidence_control
        self.origin = NativeMapHttpClient(origin).origin
        self.owner = os.getpid(), threading.get_ident()
        self.page: Any = None
        self.handler = self._receive
        self.attached = False
        self.state = "new"
        self.responses: list[Any] = []
        self.records: list[dict[str, Any]] = []
        self.next_index = 0
        self.last_readout: BrowserReadout | None = None
        self.pending_body: bytes | None = None
        self.errors: list[BaseException] = []
        self.cleanup_errors: list[BaseException] = []
        self.close_attempted = False

    def require_owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Original browser thread owns Notes capture")

    def healthy(self) -> None:
        self.require_owner()
        if self.close_attempted:
            raise InvalidTransition("Original Notes capture closed")
        if self.errors:
            raise EvidenceIntegrityError(
                "Original native Notes response capture incomplete"
            )

    def _retain(self, name: str, body: bytes, control: OperationControl) -> ReleaseFile:
        expected = ReleaseFile(
            path=name,
            sha256=hashlib.sha256(body).hexdigest(),
            size_bytes=len(body),
            executable=False,
        )
        actual = self.sink.retain(name, body, control)
        if actual != expected:
            raise EvidenceIntegrityError("Original complete Notes evidence pin differs")
        return actual

    def _record(
        self, name: str, value: dict[str, Any], control: OperationControl
    ) -> ReleaseFile:
        return self._retain(
            name,
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode(),
            control,
        )

    def attach(self, page: Any, control: OperationControl) -> None:
        self.healthy()
        if self.state != "new" or page.url != "about:blank":
            raise InvalidTransition(
                "Notes capture attaches once before original navigation"
            )
        control.checkpoint()
        self.page, self.state, self.attached = page, "active", True
        try:
            page.on("response", self.handler)
        except BaseException as error:
            self.errors.append(error)
            self.state = "failed"
            raise

    def _receive(self, response: Any) -> None:
        self.require_owner()
        try:
            parsed = urlsplit(response.url)
            request = response.request
            if (
                f"{parsed.scheme}://{parsed.netloc}" != self.origin
                or parsed.path != "/api/0.6/notes.json"
                or request.method != "GET"
                or request.resource_type != "xhr"
            ):
                return
            if self.state != "active" or self.close_attempted:
                raise InvalidTransition("Original Notes response registration closed")
            if len(self.responses) >= 256:
                raise ValueError("Original Notes response budget exceeded")
            if any(old is response for old in self.responses):
                raise InvalidTransition("Original Notes callback repeated")
            self.responses.append(response)
        except BaseException as error:
            self.errors.append(error)
            self.state = "failed"

    def observe(
        self, page: Any, readout: BrowserReadout, control: OperationControl
    ) -> None:
        self.healthy()
        if self.state != "active":
            raise InvalidTransition("Original Notes capture is not active")
        try:
            if not isinstance(readout, BrowserReadout):
                raise TypeError("Original projected browser return required")
            BrowserReadout.model_validate(readout)
            if page is not self.page or readout.scope != self.plan.scope:
                raise OwnershipConflict(
                    "Original page and scope required for Notes capture"
                )
            self.last_readout = readout
            self._drain(control)
        except BaseException as error:
            if not any(error is old for old in self.errors):
                self.errors.append(error)
            self.state = "failed"
            raise

    def _drain(self, control: OperationControl) -> None:
        while self.next_index < len(self.responses):
            index = self.next_index
            response = self.responses[index]
            # Reserve before reading: failures never permit replaying this body.
            self.next_index += 1
            row: dict[str, Any] = dict(
                schema_version="map-original-notes-response/1",
                plan_sha256=self.plan.digest,
                response_index=index,
                complete=False,
                unique_observation_sequence=(
                    self.last_readout.observation.sequence
                    if self.last_readout
                    else None
                ),
                timing_semantics="existing_response_read_after_return_or_during_close_not_new_observation",
                url=response.url,
                method=response.request.method,
                resource_type=response.request.resource_type,
                http_status=response.status,
                content_type=response.headers.get("content-type", ""),
            )
            self.records.append(row)
            primary: BaseException | None = None
            try:
                control.checkpoint()
                self.evidence_control.checkpoint()
                self._record(
                    f"map-notes-{index}-start.json", row, self.evidence_control
                )
                body = response.body()
                if type(body) is not bytes:
                    raise TypeError("Actual complete Notes response bytes required")
                self.pending_body = body
                artifact = self._retain(
                    f"map-notes-{index}.bin", body, self.evidence_control
                )
                row["body"] = artifact.model_dump(mode="json")
                self.pending_body = None
                control.checkpoint()
                row["complete"] = True
            except BaseException as error:
                primary = error
                self.errors.append(error)
                self.state = "failed"
                row["capture_error"] = "".join(traceback.format_exception(error))
            try:
                self._record(f"map-notes-{index}-end.json", row, self.evidence_control)
            except BaseException as error:
                self.errors.append(error)
                self.state = "failed"
                if primary is not None:
                    raise BaseExceptionGroup(
                        "Original Notes read and retention failures", [primary, error]
                    )
                raise
            if primary is not None:
                raise primary

    def close(self, control: OperationControl) -> None:
        self.require_owner()
        if not self.close_attempted:
            self.close_attempted = True
            if self.attached:
                self.attached = False
                try:
                    self.page.remove_listener("response", self.handler)
                except BaseException as error:
                    self.cleanup_errors.append(error)
            if not self.errors:
                try:
                    self._drain(control)
                except BaseException as error:
                    if not any(error is old for old in self.errors):
                        self.errors.append(error)
                    self.cleanup_errors.append(error)
            try:
                self._record(
                    "map-notes-close.json",
                    dict(
                        plan_sha256=self.plan.digest,
                        responses_seen=len(self.responses),
                        records=self.records,
                        pending_unattempted=len(self.responses) - self.next_index,
                        pending_body_retained=self.pending_body is not None,
                        errors=[
                            "".join(traceback.format_exception(e)) for e in self.errors
                        ],
                        cleanup_errors=[
                            "".join(traceback.format_exception(e))
                            for e in self.cleanup_errors
                        ],
                        complete=not self.errors
                        and not self.cleanup_errors
                        and self.next_index == len(self.responses),
                        task_success_or_admission_claim=False,
                    ),
                    control,
                )
            except BaseException as error:
                self.cleanup_errors.append(error)
            self.state = "closed" if not self.cleanup_errors else "failed"
        if self.cleanup_errors:
            raise BaseExceptionGroup(
                "Original Notes capture cleanup errors", self.cleanup_errors
            )
