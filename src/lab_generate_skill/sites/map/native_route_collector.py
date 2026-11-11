"""Bind actual original XHRs and unique readouts to owned native transport.

This selected process collector supplies transport evidence only. Native layer
surface/route and served-source collection, final evaluation, file publication
and production admission remain distinct consumers. No action or Observation
is created here. Fixed bootstrap must provide original plan/sink authority.
"""

import hashlib
import json
import os
import threading
import time
import traceback
from typing import Any
from urllib.parse import urlsplit
from lab_generate_skill.domain.browser_session import BrowserSessionSpec, BrowserReadout
from lab_generate_skill.domain.map_private_artifact import (
    MapPrivateArtifactPlan,
    MapArtifactPlan,
)
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    EvidenceIntegrityError,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from .native_relay import NativeMapRelay
from .native_route_request import selected_bounds, private_headers

PATTERN = "**/api/0.6/map?*"


class MapNativeRequestCollector:
    def __init__(self, plan: MapArtifactPlan, relay: NativeMapRelay) -> None:
        self.plan = MapPrivateArtifactPlan.model_validate(plan)
        if self.plan.producer != "browser_process":
            raise ValueError("Original browser process artifact plan required")
        self.relay = relay
        self.owner = os.getpid(), threading.get_ident()
        self.state = "new"
        self.page: Any = None
        self.handler = self._receive
        self.route_attempted = False
        self.closing_record_attempted = False
        self.requests: list[Any] = []
        self.readouts: list[BrowserReadout] = []
        self.last_readout: BrowserReadout | None = None
        self.errors: list[BaseException] = []
        self.cleanup_errors: list[BaseException] = []
        self.finish_record: dict[str, Any] | None = None
        self.allow_failed_readout = False

    def _owner(self) -> None:
        if (os.getpid(), threading.get_ident()) != self.owner:
            raise OwnershipConflict(
                "Original browser thread owns Map request collection"
            )

    def _record(
        self, name: str, value: dict[str, Any], *, control: OperationControl
    ) -> ReleaseFile:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
        expected = ReleaseFile(
            path=name,
            sha256=hashlib.sha256(raw).hexdigest(),
            size_bytes=len(raw),
            executable=False,
        )
        actual = self.relay.sink.retain(name, raw, control)
        if actual != expected:
            raise EvidenceIntegrityError("Original Map process record pin differs")
        return actual

    def attach(
        self, page: Any, spec: BrowserSessionSpec, control: OperationControl
    ) -> None:
        self._owner()
        if self.state != "new":
            raise InvalidTransition("Original Map process collector attaches once")
        spec = BrowserSessionSpec.model_validate(spec)
        start, origin = urlsplit(spec.task.start_url), urlsplit(self.relay.origin)
        if (
            spec.scope != self.plan.scope
            or page.url != "about:blank"
            or (start.scheme, start.netloc) != (origin.scheme, origin.netloc)
        ):
            raise OwnershipConflict(
                "Map process collector changed original scope/origin/first navigation"
            )
        control.checkpoint()
        self.page, self.state = page, "attaching"
        try:
            self.relay.start(control)
            self.route_attempted = True
            page.route(PATTERN, self.handler)
            self.state = "active"
        except BaseException as error:
            self.errors.append(error)
            self.state = "failed"
            raise

    def _receive(self, route: Any) -> None:
        self._owner()
        began = time.monotonic()
        request_id: str | None = None
        continued = False
        first_error: BaseException | None = None
        try:
            request = route.request
            bounds = selected_bounds(
                self.relay.origin, request.url, request.method, request.resource_type
            )
            if bounds is None:
                route.continue_()
                return
            if self.state != "active":
                raise InvalidTransition(
                    "Original Map request registration already sealed/failed"
                )
            if any(request is old for old in self.requests):
                raise InvalidTransition(
                    "Original browser request callback cannot be replayed"
                )
            self.requests.append(request)
            request_id = f"request-{len(self.requests)-1}"
            remaining = self.relay.evidence_control.checkpoint()
            deadline = began + min(300, remaining)
            self._record(
                request_id + "-browser-start.json",
                dict(
                    schema_version="map-actual-browser-native-request/1",
                    plan_sha256=self.plan.digest,
                    request_id=request_id,
                    actual_url=request.url,
                    method=request.method,
                    resource_type=request.resource_type,
                    requested_bbox_strings=list(bounds),
                    last_unique_observation_sequence=(
                        self.readouts[-1].observation.sequence
                        if self.readouts
                        else None
                    ),
                    timing_semantics="actual_XHR_callback_not_page_snapshot",
                    original_absolute_monotonic_deadline=deadline,
                    native_request_budget_seconds=300,
                    native_scope_or_cap_changed=False,
                ),
                control=self.relay.evidence_control,
            )
            headers = private_headers(request.headers)
            target = self.relay.register(
                request_id, bounds, deadline, self.relay.evidence_control
            )
            # No fetch, future.result, page.evaluate, renderer traversal or join.
            route.continue_(url=target, headers=headers)
            continued = True
        except BaseException as error:
            first_error = error
            self.errors.append(error)
            self.state = "failed"
            self.allow_failed_readout = True
            try:
                route.abort("failed")
            except BaseException as abort_error:
                self.errors.append(abort_error)
        finally:
            if request_id is not None:
                try:
                    self._record(
                        request_id + "-browser-end.json",
                        dict(
                            continue_returned=continued,
                            callback_seconds=time.monotonic() - began,
                            error=(
                                "".join(traceback.format_exception(first_error))
                                if first_error
                                else None
                            ),
                        ),
                        control=self.relay.evidence_control,
                    )
                except BaseException as retention_error:
                    self.errors.append(retention_error)
                    self.state = "failed"
                    self.allow_failed_readout = True

    def _healthy(self) -> None:
        if (
            self.errors
            or self.relay.registration_error
            or any(job.errors for job in self.relay.requests.values())
        ):
            self.state = "failed"
            raise EvidenceIntegrityError(
                "Original Map process/transport evidence incomplete"
            )

    def before_action(self, control: OperationControl) -> None:
        self._owner()
        if self.state != "active":
            raise InvalidTransition(
                "Original Map collection cannot accept another action"
            )
        control.checkpoint()
        self._healthy()

    def observe(
        self, page: Any, readout: BrowserReadout, control: OperationControl
    ) -> None:
        self._owner()
        if self.state != "active" and not (
            self.state == "failed" and self.allow_failed_readout
        ):
            raise InvalidTransition(
                "Original Map process cannot consume another readout"
            )
        self.allow_failed_readout = False
        try:
            if not isinstance(readout, BrowserReadout):
                raise TypeError("Original already projected BrowserReadout required")
            # Contract revalidation copies instances. Validate without replacing
            # the actual immutable object returned by the original engine.
            BrowserReadout.model_validate(readout)
            if (
                page is not self.page
                or readout.scope != self.plan.scope
                or readout.observation.sequence != len(self.readouts)
            ):
                raise OwnershipConflict(
                    "Map evidence changed original unique returned observation"
                )
            control.checkpoint()
            self.last_readout = readout
            self._record(
                f"map-observation-{readout.observation.sequence}.json",
                dict(
                    schema_version="map-native-observation-binding/1",
                    plan_sha256=self.plan.digest,
                    readout=readout.model_dump(mode="json"),
                    request_ids_seen=[
                        f"request-{i}" for i in range(len(self.requests))
                    ],
                    timing_semantics="after_unique_projected_browser_return_not_request_instant",
                ),
                control=self.relay.evidence_control,
            )
            self.readouts.append(readout)
            self._healthy()
            if readout.protocol_terminal or readout.terminated or readout.truncated:
                # Return this unique action observation before waiting for network
                # completion. Only the existing explicit capture may settle it.
                self.state = "terminal_pending"
        except BaseException as error:
            self.errors.append(error)
            self.state = "failed"
            raise

    def finish(self, control: OperationControl) -> None:
        """Explicit final private capture also covers interaction/generation limits."""
        self._owner()
        if self.state == "terminal":
            return
        if self.state not in ("active", "terminal_pending"):
            raise InvalidTransition("Original Map process cannot be sealed again")
        control.checkpoint()
        self._healthy()
        self.state = "settling"
        jobs = tuple(self.relay.requests.values())
        self.finish_record = dict(
            schema_version="map-existing-native-pending-settle/1",
            request_ids=[job.exchange.request_id for job in jobs],
            new_requests_created=False,
            new_observation_created=False,
            original_deadlines_extended=False,
            passed=False,
        )
        primary: BaseException | None = None
        try:
            while any(not job.finished for job in jobs):
                remaining = min(
                    control.checkpoint(),
                    min(
                        job.exchange.deadline - time.monotonic()
                        for job in jobs
                        if not job.finished
                    ),
                )
                if remaining <= 0:
                    raise TimeoutError(
                        "Original pending native request deadline expired"
                    )
                self.page.wait_for_timeout(min(50, remaining * 1000))
            self._healthy()
            if jobs:
                remaining = min(
                    control.checkpoint(),
                    min(job.exchange.deadline - time.monotonic() for job in jobs),
                )
                if remaining <= 0:
                    raise TimeoutError("Original native renderer deadline expired")
                self.page.wait_for_function(
                    "() => !window.jQuery || jQuery.active === 0",
                    timeout=remaining * 1000,
                )
            self.finish_record["passed"] = True
            self.state = "terminal"
        except BaseException as error:
            primary = error
            self.errors.append(error)
            self.state = "failed"
            self.finish_record["error"] = "".join(traceback.format_exception(error))
            raise
        finally:
            try:
                self._record(
                    "map-existing-pending-finish.json",
                    self.finish_record,
                    control=self.relay.evidence_control,
                )
            except BaseException as error:
                self.errors.append(error)
                self.state = "failed"
                if primary is not None:
                    raise BaseExceptionGroup(
                        "Original native settle and retention failures",
                        [primary, error],
                    )
                raise

    def close(self, control: OperationControl) -> None:
        self._owner()
        if self.state == "closed":
            return
        self.state = "closing"
        errors: list[BaseException] = []
        if self.route_attempted:
            self.route_attempted = False
            try:
                self.page.unroute(PATTERN, self.handler)
            except BaseException as error:
                errors.append(error)
        try:
            self.relay.close(control)
        except BaseException as error:
            errors.append(error)
        if not self.closing_record_attempted:
            self.closing_record_attempted = True
            try:
                self._record(
                    "map-process-close.json",
                    dict(
                        original_relay_physical_closed=self.relay.physical_closed,
                        request_count=len(self.requests),
                        unique_readout_count=len(self.readouts),
                        process_errors=[
                            "".join(traceback.format_exception(e)) for e in self.errors
                        ],
                        cleanup_errors=[
                            "".join(traceback.format_exception(e)) for e in errors
                        ],
                        task_success_or_admission_claim=False,
                    ),
                    control=control,
                )
            except BaseException as error:
                errors.append(error)
        self.cleanup_errors.extend(errors)
        self.state = "failed" if self.cleanup_errors else "closed"
        if self.cleanup_errors:
            raise BaseExceptionGroup(
                "Original Map collector cleanup failures", self.cleanup_errors
            )
