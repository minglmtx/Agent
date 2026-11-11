"""Initial qualification consumes original return and full readiness without new observation."""

from datetime import timedelta, datetime, timezone
import json
from pathlib import Path
import pytest
from lab_generate_skill.domain.map_initial_capture import (
    MapInitialCapture,
    MapInitialEvidence,
)
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    EvidenceIntegrityError,
    EvidenceNotFound,
    OperationStopped,
)
from lab_generate_skill.sites.map.tasks.overlay_initial_observation import (
    OverlayInitialObservationChecks,
)
from map_registered_worker_fixtures import RegisteredMapCase
from map_initial_records_fixtures import initial
from preparation_record_fixtures import put
from test_map_registered_worker import registered_map as registered_map
from site_instance_fixtures import node_path as node_path
from test_map_browser_collection import capture
from test_slurm_commands import guard


def test_original_initial_checks_publish_reconcile_and_terminal_capture(
    registered_map: RegisteredMapCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    with initial(registered_map, monkeypatch) as c:
        b = c.browser
        assert (
            b.engine is not None
            and b.collector is not None
            and b.collector.native is not None
        )
        first = b.engine.last_readout
        calls = list(b.calls)
        reads = b.page.reads
        ref = c.records.publish(c.selection, c.operation)
        checked = c.records.load(c.selection, ref, c.operation)
        assert checked.checks.status == "pass" and checked.checks.required == (
            "map.initial.observation",
            "map.initial.native_ready",
        )
        cleanup = c.operation.cleanup(
            "reconcile-initial", now=datetime.now(timezone.utc), seconds=20
        )
        assert c.records.load(c.selection, ref, cleanup) == checked
        assert (
            b.engine.last_readout is first
            and b.calls == calls
            and b.page.reads == reads
        )
        assert (
            b.collector.state == "active"
            and not b.collector.native.requests.relay.physical_closed
        )
        assert c.preparation.environment.checks.status == "unknown"
        returned = c.records.reader.load(
            c.selection, c.operation, guard()
        ).acquired.details.started
        assert checked.observation_ref == returned.initial_observation_ref
        terminal, request = capture(b, c.session)
        terminal.capture(request, control=guard(30))
        assert b.engine.last_readout is first and b.collector.state == "published"
        assert b.calls.count("project") == 1


@pytest.mark.parametrize(
    "fault",
    [
        "configuration",
        "request",
        "selector",
        "readout",
        "plan",
        "early-time",
        "missing",
        "corrupt",
        "cancel",
    ],
)
def test_original_capture_faults_cannot_publish_initial_pass(
    fault: str, registered_map: RegisteredMapCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    with initial(registered_map, monkeypatch) as c:
        b = c.browser
        store = b.resource.evidence
        inputs = c.records.reader.load(c.selection, c.operation, guard())
        intent, result = c.intent, c.result
        if fault == "configuration":
            intent = intent.model_copy(update={"configuration_sha256": "f" * 64})
        if fault == "request":
            result = result.model_copy(update={"request_sha256": "f" * 64})
        if fault == "selector":
            request = intent.request.model_copy(
                update={"collector_id": "map-native-process"}
            )
            intent = intent.model_copy(update={"request": request})
            result = result.model_copy(update={"request_sha256": request.digest})
        if fault in ("readout", "plan"):
            proof = MapInitialCapture.model_validate_json(result.private_result)
            proof = proof.model_copy(
                update=(
                    {"readout_sha256": "f" * 64}
                    if fault == "readout"
                    else {
                        "plan": proof.plan.model_copy(update={"artifact_id": "foreign"})
                    }
                )
            )
            result = result.model_copy(
                update={"private_result": proof.model_dump_json()}
            )
        if fault == "early-time":
            result = result.model_copy(
                update={
                    "captured_at": inputs.returned.observation.captured_at
                    - timedelta(seconds=1)
                }
            )
        evidence = MapInitialEvidence(
            intent_ref=put(store, intent), result_ref=put(store, result)
        )
        if fault in ("missing", "corrupt"):
            path = (
                registered_map.workspace / "evidence/blobs" / evidence.result_ref.sha256
            )
            if fault == "missing":
                path.unlink()
            else:
                path.write_bytes(b"corrupt")
        from lab_generate_skill.domain.map_browser_initialization import (
            MapNativeInitialization,
        )

        checks = OverlayInitialObservationChecks(
            store,
            evidence,
            MapNativeInitialization.model_validate(b.configuration.initialization),
        )

        class Cancel:
            def checkpoint(self) -> float:
                raise OperationStopped("CANCELLED", "initial-checks")

            def wait(self, seconds: float) -> None:
                self.checkpoint()

        calls = list(b.calls)
        reads = b.page.reads
        with pytest.raises(
            (
                ValueError,
                OwnershipConflict,
                EvidenceIntegrityError,
                EvidenceNotFound,
                OperationStopped,
            )
        ):
            checks.check(inputs, Cancel() if fault == "cancel" else guard())
        assert b.calls == calls and b.page.reads == reads
        assert b.collector is not None and b.collector.state == "active"


def test_initial_evidence_requires_original_private_references() -> None:
    from test_core_contracts import reference

    original = MapInitialEvidence(
        intent_ref=reference("private", "browser-capture-intent/1"),
        result_ref=reference("private", "browser-capture-result/1"),
    )
    for field in ("intent_ref", "result_ref"):
        ref = getattr(original, field)
        for altered in (
            None,
            0,
            "",
            ref.model_copy(update={"visibility": "public"}),
            ref.model_copy(update={"content_schema": "other/1"}),
        ):
            with pytest.raises(ValueError):
                MapInitialEvidence.model_validate(
                    original.model_copy(update={field: altered})
                )
