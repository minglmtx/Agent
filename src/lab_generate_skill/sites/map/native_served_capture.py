"""Once-only proof from original browser script responses and runtime functions.

Callbacks retain handles only. Body reads use the browser's existing responses,
never another HTTP request. Native blocking reads remain supervised by the
original browser worker; OperationControl guards their boundaries.
"""

from collections.abc import Mapping
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
from .native_served_rules import (
    RENDERER_READ,
    candidate_names,
    matched_sources,
    reviewed_sources,
)


class NativeServedCapture:
    def __init__(
        self,
        plan: MapArtifactPlan,
        sink: MapArtifactSink,
        evidence_control: OperationControl,
        origin: str,
        originals: Mapping[str, bytes],
        tile_url: str,
    ) -> None:
        self.plan = MapPrivateArtifactPlan.model_validate(plan)
        if self.plan.producer != "browser_process":
            raise ValueError("Original browser process artifact plan required")
        self.sink, self.evidence_control = sink, evidence_control
        self.origin = NativeMapHttpClient(origin).origin
        if not isinstance(originals, Mapping):
            raise ValueError("Exactly the four original native sources required")
        snapshot = dict(originals)
        self.expected = reviewed_sources(snapshot, tile_url)
        self.original_source_pins = {
            name: hashlib.sha256(raw).hexdigest() for name, raw in snapshot.items()
        }
        self.tile_url = tile_url
        self.owner = os.getpid(), threading.get_ident()
        self.page: Any = None
        self.responses: list[Any] = []
        self.handler = self._receive
        self.attached = False
        self.state = "new"
        self.errors: list[BaseException] = []
        self.cleanup_errors: list[BaseException] = []
        self.summary: dict[str, Any] | None = None
        self.pending_body: bytes | None = None
        self.close_attempted = False

    def require_owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Original browser thread owns served source proof")

    def healthy(self) -> None:
        self.require_owner()
        if self.close_attempted:
            raise InvalidTransition("Original served source collector closed")
        if self.errors:
            raise EvidenceIntegrityError("Original served source proof failed")

    def _retain(self, name: str, body: bytes, control: OperationControl) -> ReleaseFile:
        expected = ReleaseFile(
            path=name,
            sha256=hashlib.sha256(body).hexdigest(),
            size_bytes=len(body),
            executable=False,
        )
        actual = self.sink.retain(name, body, control)
        if actual != expected:
            raise EvidenceIntegrityError("Complete served source evidence pin differs")
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
                "Served sources attach once before original navigation"
            )
        control.checkpoint()
        self.page, self.state, self.attached = page, "collecting", True
        try:
            page.on("response", self.handler)
        except BaseException as error:
            self.errors.append(error)
            self.state = "failed"
            raise

    def _receive(self, response: Any) -> None:
        self.require_owner()
        try:
            if response.request.resource_type != "script" or not candidate_names(
                response.url
            ):
                return
            if self.state != "collecting":
                raise InvalidTransition("Original served response registration closed")
            if len(self.responses) >= 256:
                raise ValueError("Original served candidate response budget exceeded")
            if any(old is response for old in self.responses):
                raise InvalidTransition("Original script response callback repeated")
            self.responses.append(response)
        except BaseException as error:
            self.errors.append(error)
            self.state = "failed"

    def _detach(self) -> None:
        if self.attached:
            self.attached = False
            self.page.remove_listener("response", self.handler)

    def verify(
        self, page: Any, readout: BrowserReadout, control: OperationControl
    ) -> None:
        self.healthy()
        if self.state != "collecting":
            raise InvalidTransition("Original served source verification occurs once")
        self.state = "verifying"
        self.summary = dict(
            schema_version="map-original-actually-served/1",
            plan_sha256=self.plan.digest,
            passed=False,
            responses=[],
            expected_sources=[name for name, _ in self.expected.sources],
            original_source_pins=self.original_source_pins,
            expected_source_pins={
                name: hashlib.sha256(source.encode()).hexdigest()
                for name, source in self.expected.sources
            },
            private_tile_origin=self.tile_url,
            matched_sources=[],
            actual_renderer_functions=None,
            source_only_claim=False,
            task_admission_claim=False,
            new_requests_or_observations=False,
        )
        primary: BaseException | None = None
        try:
            if not isinstance(readout, BrowserReadout):
                raise TypeError("Original already projected browser readout required")
            BrowserReadout.model_validate(readout)
            if page is not self.page or readout.scope != self.plan.scope:
                raise OwnershipConflict(
                    "Original page/readout scope required for served proof"
                )
            self.summary["original_readout"] = readout.model_dump(mode="json")
            control.checkpoint()
            self._detach()
            found: set[str] = set()
            for index, response in enumerate(self.responses):
                control.checkpoint()
                parsed = urlsplit(response.url)
                record: dict[str, Any] = dict(
                    actual_url=response.url,
                    http_status=response.status,
                    resource_type=response.request.resource_type,
                    original_main_frame=response.request.frame is page.main_frame,
                    from_service_worker=response.from_service_worker,
                    required_sources=list(candidate_names(response.url)),
                )
                self.summary["responses"].append(record)
                self._record(
                    f"map-served-{index}-start.json", record, self.evidence_control
                )
                body = response.body()
                if type(body) is not bytes:
                    raise TypeError("Actual browser complete response bytes required")
                self.pending_body = body
                artifact = self._retain(
                    f"map-served-{index}.js", body, self.evidence_control
                )
                record["body"] = artifact.model_dump(mode="json")
                self.pending_body = None
                if (
                    f"{parsed.scheme}://{parsed.netloc}" != self.origin
                    or parsed.fragment
                    or parsed.username is not None
                    or parsed.password is not None
                    or type(response.status) is not int
                    or response.status != 200
                    or record["original_main_frame"] is not True
                    or response.from_service_worker is not False
                ):
                    raise EvidenceIntegrityError(
                        "Actual native script origin/status/frame differs"
                    )
                matched = matched_sources(self.expected, body)
                record["full_reviewed_executable_sources_present"] = list(matched)
                if any(name not in matched for name in record["required_sources"]):
                    raise EvidenceIntegrityError(
                        "Actual script lacks its complete reviewed executable source"
                    )
                found.update(matched)
                self.summary["matched_sources"] = sorted(found)
            if found != set(self.summary["expected_sources"]):
                raise EvidenceIntegrityError(
                    "Original browser did not load every complete native source"
                )
            control.checkpoint()
            actual = page.evaluate(RENDERER_READ)
            self.summary["actual_renderer_functions"] = actual
            if actual != dict(self.expected.renderer_functions):
                raise EvidenceIntegrityError(
                    "Actually loaded renderer functions differ"
                )
            control.checkpoint()
            self.summary["passed"] = True
        except BaseException as error:
            primary = error
            self.errors.append(error)
            self.state = "failed"
            self.summary["error"] = "".join(traceback.format_exception(error))
        try:
            self._record(
                "map-actually-served.json", self.summary, self.evidence_control
            )
        except BaseException as error:
            self.errors.append(error)
            self.state = "failed"
            if primary is not None:
                raise BaseExceptionGroup(
                    "Original served source and retention errors", [primary, error]
                )
            raise
        if primary is not None:
            raise primary
        self.state = "verified"

    def close(self, control: OperationControl) -> None:
        self.require_owner()
        if not self.close_attempted:
            self.close_attempted = True
            try:
                self._detach()
            except BaseException as error:
                self.cleanup_errors.append(error)
            try:
                self._record(
                    "map-served-close.json",
                    dict(
                        plan_sha256=self.plan.digest,
                        final_state=self.state,
                        responses_seen=len(self.responses),
                        pending_body_retained=self.pending_body is not None,
                        errors=[
                            "".join(traceback.format_exception(e)) for e in self.errors
                        ],
                        cleanup_errors=[
                            "".join(traceback.format_exception(e))
                            for e in self.cleanup_errors
                        ],
                        task_success_or_admission_claim=False,
                    ),
                    control,
                )
            except BaseException as error:
                self.cleanup_errors.append(error)
        if self.cleanup_errors:
            raise BaseExceptionGroup(
                "Original served proof closure errors", self.cleanup_errors
            )
