"""Actual selected passive captures through the single durable browser port."""

from datetime import datetime, timezone, timedelta
from typing import Literal
from uuid import uuid4
import hashlib
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from lab_generate_skill.adapters.browsergym.worker_client import (
    SupervisedBrowserSession,
)
from lab_generate_skill.adapters.browsergym.recorded_capture import (
    RecordedBrowserCapture,
)
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureRequest,
    BrowserCaptureIntent,
)
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.evidence_schema import MapCapturePair
from browser_resource_fixtures import ResourceCase


def capture(
    browser: ResourceCase,
    session: EvidenceBrowserSession,
    collector: Literal[
        "map-initial-readiness",
        "map-native-process",
        "map-page-health",
        "map-navigation-initial",
        "map-navigation-page-health",
    ],
) -> MapCapturePair:
    if collector not in (
        "map-initial-readiness",
        "map-native-process",
        "map-page-health",
        "map-navigation-initial",
        "map-navigation-page-health",
    ):
        raise ValueError("Unsupported selected Map passive capture")
    if session.observation_ref is None or not isinstance(
        session.engine, SupervisedBrowserSession
    ):
        raise ValueError("Original fixed browser return required")
    request = BrowserCaptureRequest(
        scope=browser.spec.configuration.spec.scope,
        operation=browser.op.model_copy(
            update={
                "operation_id": "selected-" + collector,
                # Preserve the original native batch allowance. The collector
                # still intersects this with each original absolute deadline.
                "deadline": datetime.now(timezone.utc)
                + timedelta(seconds=300 if collector == "map-native-process" else 180),
            }
        ),
        observation_sha256=session.observation_ref.sha256,
        collector_id=collector,
        collector_version="1",
    )

    class Authority:
        def verify_capture(
            self,
            configuration: BrowserWorkerConfiguration,
            req: BrowserCaptureRequest,
            intent_ref: EvidenceRef,
            control: OperationControl,
        ) -> None:
            control.checkpoint()
            intent = BrowserCaptureIntent.model_validate_json(
                browser.evidence.read(intent_ref, control)
            )
            if (
                configuration != browser.spec.configuration
                or req != request
                or session.observation_ref is None
                or req.observation_sha256 != session.observation_ref.sha256
                or intent.request != req
                or intent.configuration_sha256
                != hashlib.sha256(configuration.model_dump_json().encode()).hexdigest()
            ):
                raise OwnershipConflict(
                    "Original Map observation/capture intent changed"
                )
            read = req.operation.cleanup(
                "map-capture-read-" + uuid4().hex,
                now=datetime.now(timezone.utc),
                seconds=10,
            )
            if browser.journal.read(browser.spec.token, read).state != "acquired":
                raise OwnershipConflict("Original Map browser is not acquired")
            control.checkpoint()

    recorder = RecordedBrowserCapture(session.engine, browser.evidence, Authority())
    result = recorder.capture(request, control=browser.controls.bind(request.operation))
    assert recorder.intent_ref is not None
    return MapCapturePair(intent_ref=recorder.intent_ref, result_ref=result)
