"""Original Map preparation/resource/capture/initial-check graph, explicit native doubles."""

from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import dataclass
import pytest
from lab_generate_skill.adapters.sites.resource import RegisteredSite
from lab_generate_skill.adapters.browsergym.resource import registered_browser
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from lab_generate_skill.adapters.storage.initial_observations import (
    EvidenceInitialObservations,
)
from lab_generate_skill.bootstrap.map_initial_observation import (
    map_initial_observations,
)
from lab_generate_skill.domain.map_initial_capture import MapInitialEvidence
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from map_registered_worker_fixtures import RegisteredMapCase
from map_prepared_records_fixtures import prepare, PreparedMapCase
from map_prepared_browser_fixtures import bind
from map_browser_collection_fixtures import CollectionCase
from test_map_browser_collection import capture
from initial_observation_fixtures import Authority
from test_site_resource import enter
from test_slurm_commands import guard


@dataclass
class InitialCase:
    live: RegisteredSite
    browser: CollectionCase
    session: EvidenceBrowserSession
    preparation: PreparedMapCase
    selection: InitialObservationSelection
    records: EvidenceInitialObservations
    evidence: MapInitialEvidence
    intent: BrowserCaptureIntent
    result: BrowserCaptureResult
    operation: OperationContext


@contextmanager
def initial(c: RegisteredMapCase, patch: pytest.MonkeyPatch) -> Iterator[InitialCase]:
    with enter(c.resource) as live:
        p = prepare(c, live)
        with initial_prepared(c, patch, live, p) as selected:
            yield selected


@contextmanager
def initial_prepared(
    c: RegisteredMapCase,
    patch: pytest.MonkeyPatch,
    live: RegisteredSite,
    p: PreparedMapCase,
    *,
    browser_case: CollectionCase | None = None,
) -> Iterator[InitialCase]:
    b, binding, authority = bind(c, p, live, patch, browser=browser_case)
    c.observer = "controller"
    try:
        with registered_browser(
            b.resource.spec,
            b.resource.op,
            journal=b.resource.journal,
            evidence=b.resource.evidence,
            controls=b.resource.controls,
            clock=b.resource.clock,
            authority=authority,
        ) as browser:
            recorder, request = capture(b, browser)
            request = request.model_copy(
                update={
                    "collector_id": "map-initial-readiness",
                    "operation": request.operation.model_copy(
                        update={"operation_id": "initial-native-capture"}
                    ),
                }
            )
            result_ref = recorder.capture(request, control=guard())
            assert recorder.intent_ref is not None and recorder.result is not None
            evidence = MapInitialEvidence(
                intent_ref=recorder.intent_ref, result_ref=result_ref
            )
            record = b.resource.journal.read(b.resource.spec.token, b.resource.op)
            acquire = ResourceAcquisitionIntent.model_validate_json(
                b.resource.evidence.read(record.events[1].evidence[0])
            )
            assert browser.resource_started_ref is not None
            selected = InitialObservationSelection(
                preparation=p.publication,
                browser_spec_ref=acquire.configuration_ref,
                browser_acquired_ref=browser.resource_started_ref,
            )
            records = map_initial_observations(
                b.resource.evidence,
                b.resource.controls,
                p.records,
                Authority(selected),
                evidence,
                initialization=b.configuration.initialization,
            )
            intent = BrowserCaptureIntent.model_validate_json(
                b.resource.evidence.read(evidence.intent_ref)
            )
            yield InitialCase(
                live,
                b,
                browser,
                p,
                selected,
                records,
                evidence,
                intent,
                recorder.result,
                b.resource.op.model_copy(
                    update={"operation_id": "original-initial-checks"}
                ),
            )
    finally:
        c.observer = "worker"
