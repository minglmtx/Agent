"""Original unique0/frame/journal/CAS initial consumer; native effects are doubles."""

import json
from pathlib import Path
from datetime import datetime, timezone
import pytest
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.domain.map_initial_capture import MapInitialEvidence
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    EvidenceIntegrityError,
    OperationStopped,
)
from lab_generate_skill.sites.map.tasks.navigation_initial_observation import (
    NavigationInitialObservationChecks,
)
from lab_generate_skill.sites.map.navigation_initial_evidence import (
    NavigationInitialReadiness,
)
from lab_generate_skill.sites.map.navigation_initial_readiness_rules import (
    original_navigation_readiness,
)
from lab_generate_skill.sites.map.navigation_browser_initialization import (
    MapNavigationBrowserInitializer,
)
from map_navigation_browser_fixtures import selection, Page, Clock, CancelledControl
from map_navigation_initial_fixtures import initial_navigation
from map_navigation_group_cases import SOURCES
from map_registered_worker_fixtures import RegisteredMapCase
from map_qualification_fixtures import qualified, restore
from preparation_record_fixtures import put
from site_instance_fixtures import node_path as node_path
from test_site_resource import inspect
from test_slurm_commands import guard


@pytest.mark.parametrize("source", SOURCES)
def test_each_member_original_unique0_capture_bind_publish_read_close_and_reset(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=source)
    try:
        with qualified(c, monkeypatch) as q:
            with initial_navigation(c, q, monkeypatch) as n:
                first = n.engine.last_readout
                calls = list(n.calls)
                samples = list(n.page.calls)
                ref = n.records.publish(n.selection, n.operation)
                checked = n.records.load(n.selection, ref, n.operation)
                assert checked.checks.status == "pass"
                assert checked.checks.required == (
                    "map.navigation.initial.observation",
                    "map.navigation.initial.document_ready",
                )
                assert n.session.observation_ref == checked.observation_ref
                cleanup = n.operation.cleanup(
                    "read-original-navigation-initial",
                    now=datetime.now(timezone.utc),
                    seconds=20,
                )
                assert n.records.load(n.selection, ref, cleanup) == checked
                assert (
                    n.engine.last_readout is first
                    and first is not None
                    and first.observation.sequence == 0
                )
                assert (
                    n.calls == calls
                    and n.page.calls == samples
                    and n.calls.count("project") == 1
                )
                records = n.records
                selected = n.selection
                operation = n.operation
            assert n.engine.state == "closed"
            record = n.browser.journal.read(n.browser.spec.token, n.browser.op)
            assert record.state == "closed"
            ending = json.loads(n.browser.evidence.read(record.events[-1].evidence[0]))
            closure = ClosureReceipt.model_validate_json(
                json.dumps(ending["details"]["closure"])
            )
            assert (
                closure.status == "closed"
                and closure.token == q.plan.attempt_allocations[0]
            )
            reset = restore(q, closure_refs=(put(c.resource.evidence, closure),))
            assert (
                q.qualifications.checks.reset(
                    reset, put(c.resource.evidence, reset), guard()
                ).health.status
                == "pass"
            )
        assert inspect(c.resource).state == "closed"
        c.observer = "controller"
        assert (
            records.load(
                selected,
                ref,
                operation.cleanup(
                    "closed-original-initial",
                    now=datetime.now(timezone.utc),
                    seconds=20,
                ),
            )
            == checked
        )
    finally:
        c.close_sockets()


@pytest.mark.parametrize(
    "fault",
    [
        "configuration",
        "request",
        "selector",
        "old-observation",
        "early-time",
        "proof-config",
        "wrong-start",
        "native-center",
        "cancel",
    ],
)
def test_capture_binding_faults_cannot_turn_into_initial_pass(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=SOURCES[0])
    try:
        with qualified(c, monkeypatch) as q:
            with initial_navigation(c, q, monkeypatch) as n:
                store = n.browser.evidence
                inputs = n.records.reader.load(n.selection, n.operation, guard())
                intent = BrowserCaptureIntent.model_validate_json(
                    store.read(n.evidence.intent_ref)
                )
                result = BrowserCaptureResult.model_validate_json(
                    store.read(n.evidence.result_ref)
                )
                cfg = inputs.browser.configuration.initialization
                from lab_generate_skill.domain.map_navigation_browser_initialization import (
                    MapNavigationInitialization,
                )

                assert isinstance(cfg, MapNavigationInitialization)
                if fault == "configuration":
                    intent = intent.model_copy(
                        update={"configuration_sha256": "f" * 64}
                    )
                if fault == "request":
                    result = result.model_copy(update={"request_sha256": "f" * 64})
                if fault in ("selector", "old-observation"):
                    request = intent.request.model_copy(
                        update=(
                            {"collector_id": "map-initial-readiness"}
                            if fault == "selector"
                            else {"observation_sha256": "f" * 64}
                        )
                    )
                    intent = intent.model_copy(update={"request": request})
                    result = result.model_copy(
                        update={"request_sha256": request.digest}
                    )
                if fault == "early-time":
                    from datetime import timedelta

                    result = result.model_copy(
                        update={
                            "captured_at": inputs.returned.observation.captured_at
                            - timedelta(seconds=1)
                        }
                    )
                if fault in ("proof-config", "wrong-start", "native-center"):
                    proof = NavigationInitialReadiness.model_validate_json(
                        result.private_result
                    )
                    if fault == "proof-config":
                        proof = proof.model_copy(
                            update={
                                "initialization": cfg.model_copy(
                                    update={
                                        "site_ref": cfg.site_ref.model_copy(
                                            update={"producer": "other"}
                                        )
                                    }
                                )
                            }
                        )
                    if fault == "wrong-start":
                        proof = proof.model_copy(
                            update={"start_url": cfg.endpoint + "about"}
                        )
                    if fault == "native-center":
                        assert proof.native_signal_json is not None
                        signal = json.loads(proof.native_signal_json)
                        signal["geo"] = "geo:0,0?z=7"
                        proof = proof.model_copy(
                            update={"native_signal_json": json.dumps(signal)}
                        )
                    result = result.model_copy(
                        update={"private_result": proof.model_dump_json()}
                    )
                evidence = MapInitialEvidence(
                    intent_ref=put(store, intent), result_ref=put(store, result)
                )
                checker = NavigationInitialObservationChecks(store, evidence, cfg)
                calls = list(n.calls)
                samples = list(n.page.calls)
                with pytest.raises(
                    (
                        ValueError,
                        OwnershipConflict,
                        EvidenceIntegrityError,
                        OperationStopped,
                    )
                ):
                    checker.check(
                        inputs, CancelledControl() if fault == "cancel" else guard()
                    )
                assert n.calls == calls and n.page.calls == samples
    finally:
        c.close_sockets()


@pytest.mark.parametrize("source", [SOURCES[0], SOURCES[-1]])
@pytest.mark.parametrize(
    "fault",
    [
        "http",
        "document",
        "partial",
        "extra-map",
        "short-stable",
        "wrong-target",
        "consistent-wrong-center",
    ],
)
def test_readiness_requires_complete_original_facts_and_exact_plain_map(
    source: str, fault: str
) -> None:
    cfg, public = selection(source)
    clock = Clock()
    page = Page(clock)
    init = MapNavigationBrowserInitializer(cfg, clock)
    init.setup(page, public, guard())
    proof = init.fact
    assert proof is not None
    if fault == "http":
        proof = proof.model_copy(
            update={
                "page": proof.page.model_copy(
                    update={
                        "health": proof.page.health.model_copy(
                            update={"http_status": None, "status_source": "unavailable"}
                        )
                    }
                )
            }
        )
    if fault == "document":
        proof = proof.model_copy(
            update={"page": proof.page.model_copy(update={"document_state": "loading"})}
        )
    if fault == "partial":
        proof = (
            proof.model_copy(update={"native_view_json": None})
            if source == SOURCES[0]
            else proof.model_copy(
                update={
                    "page": proof.page.model_copy(
                        update={
                            "health": proof.page.health.model_copy(
                                update={
                                    "url": cfg.endpoint + "about",
                                    "sampled_url": cfg.endpoint + "about",
                                }
                            )
                        }
                    )
                }
            )
        )
    if fault == "extra-map":
        proof = proof.model_copy(update={"native_signal_json": "{}"})
    if fault == "short-stable":
        proof = proof.model_copy(
            update={"stable_seconds": 0.1 if source == SOURCES[0] else 1.0}
        )
    if fault == "wrong-target":
        proof = proof.model_copy(update={"start_url": cfg.endpoint + "help"})
    if fault == "consistent-wrong-center":
        if source == SOURCES[0]:
            assert (
                proof.native_signal_json is not None
                and proof.native_view_json is not None
            )
            signal = json.loads(proof.native_signal_json)
            view = json.loads(proof.native_view_json)
            signal.update(geo="geo:0,0?z=7", long="/#map=7/0/0")
            view.update(native_geo_uri=signal["geo"], native_long_link=signal["long"])
            proof = proof.model_copy(
                update={
                    "native_signal_json": json.dumps(signal),
                    "native_view_json": json.dumps(view),
                }
            )
        else:
            proof = proof.model_copy(update={"stable_seconds": 0.75})
    with pytest.raises((ValueError, EvidenceIntegrityError)):
        original_navigation_readiness(proof, public)


@pytest.mark.parametrize("seconds", [0.75, 45.0])
def test_original_plain_readiness_stability_boundaries_are_inclusive(
    seconds: float,
) -> None:
    cfg, public = selection(SOURCES[0])
    clock = Clock()
    page = Page(clock)
    init = MapNavigationBrowserInitializer(cfg, clock)
    init.setup(page, public, guard())
    assert init.fact is not None
    original_navigation_readiness(
        init.fact.model_copy(update={"stable_seconds": seconds}), public
    )
