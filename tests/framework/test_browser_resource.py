"""Once-only acquisition and truthful cleanup with real persistent journals."""

from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
import uuid
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.browsergym.resource import registered_browser
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from lab_generate_skill.adapters.browsergym.return_publication import (
    BrowserReturnPublication,
)
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    OperationContext,
    ResourceRecord,
    ResourceState,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from browser_resource_fixtures import resource_case, ResourceCase, ResourceChannel
from browser_worker_fixtures import action
from test_resource_journal import context


@pytest.fixture
def c(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ResourceCase:
    return resource_case(tmp_path, monkeypatch)


def enter(
    c: ResourceCase, publication: BrowserReturnPublication | None = None
) -> AbstractContextManager[EvidenceBrowserSession]:
    return registered_browser(
        c.spec,
        c.op,
        journal=c.journal,
        evidence=c.evidence,
        controls=c.controls,
        clock=c.clock,
        authority=c.authority,
        return_publication=publication,
    )


def inspect(c: ResourceCase) -> ResourceRecord:
    op = c.op.cleanup(
        "inspect-" + uuid.uuid4().hex, now=datetime.now(timezone.utc), seconds=30
    )
    return c.journal.read(c.spec.token, op)


@pytest.mark.parametrize("independent_return", [False, True])
def test_registered_start_action_close_and_repeat(
    c: ResourceCase, independent_return: bool
) -> None:
    publication = (
        BrowserReturnPublication(c.spec.token, c.controls, c.clock, 30)
        if independent_return
        else None
    )
    with enter(c, publication) as browser:
        assert browser.return_publication is publication
        assert inspect(c).state == "acquired" and browser.observation_ref is not None
        step = context(c.spec.token, "step")
        result = browser.step(action(), step, control=c.controls.bind(step))
        assert result.action_id == action().action_id
        if publication is not None:
            assert publication.used == {step.operation_id}
    assert [e.state for e in inspect(c).events] == [
        "registered",
        "acquiring",
        "acquired",
        "closing",
        "closed",
    ]
    with pytest.raises(DispatchAlreadyCommitted):
        with enter(c):
            pytest.fail("duplicate launch")
    assert (
        sum(x.starts for x in c.channels) == 1
        and sum(x.finishes for x in c.channels) == 1
    )


@pytest.mark.parametrize("phase", ["start", "started", "closure"])
def test_authority_denial_has_no_false_success(c: ResourceCase, phase: str) -> None:
    if phase == "start":
        c.authority.deny_start = True
    elif phase == "started":
        c.authority.deny_started = True
    else:
        c.authority.deny_close = True
    with pytest.raises((PermissionError, BaseExceptionGroup)):
        with enter(c):
            pass
    if phase == "start":
        assert not c.channels and not list(c.journal._root.iterdir())
    else:
        assert c.channels[0].capture.termination is not None
        assert inspect(c).state == ("closed" if phase == "started" else "quarantined")


def test_lost_begin_ack_has_no_launch_or_cleanup(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = c.journal.begin_acquire

    def lost(
        token: AllocationToken, ref: EvidenceRef, revision: int, op: OperationContext
    ) -> ResourceRecord:
        original(token, ref, revision, op)
        raise OSError("begin committed but reply lost")

    monkeypatch.setattr(c.journal, "begin_acquire", lost)
    with pytest.raises(OSError):
        with enter(c):
            pytest.fail("unknown launch permission")
    assert (
        inspect(c).state == "acquiring"
        and c.channels[0].starts == 0
        and c.channels[0].aborts == 0
        and c.authority.close_calls == 0
    )


@pytest.mark.parametrize("state", ["acquired", "closing", "closed"])
def test_bookkeeping_failure_still_closes_original(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    original = c.journal.advance

    def fail(
        token: AllocationToken,
        value: ResourceState,
        refs: tuple[EvidenceRef, ...],
        revision: int,
        op: OperationContext,
    ) -> ResourceRecord:
        if value == state:
            raise OSError("failed " + state)
        return original(token, value, refs, revision, op)

    monkeypatch.setattr(c.journal, "advance", fail)
    with pytest.raises((OSError, BaseExceptionGroup)) as caught:
        with enter(c):
            pass
    assert c.channels[0].capture.termination is not None
    assert c.channels[0].service.closed
    if state == "acquired":
        # Ownership now commits before the factory/start command.
        assert c.channels[0].engine.state == "new" and c.channels[0].engine.calls == []
    else:
        assert c.channels[0].engine.state == "closed"
    assert getattr(caught.value, "command_capture").termination.state == "reaped"
    if state != "acquired":
        assert getattr(caught.value, "browser_resource_ending_ref") is not None


def test_body_error_remains_first_while_unconfirmed_closure_quarantines(
    c: ResourceCase,
) -> None:
    primary = ValueError("body failure")
    c.authority.deny_close = True
    with pytest.raises(BaseExceptionGroup) as caught:
        with enter(c):
            raise primary
    assert caught.value.exceptions[0] is primary and inspect(c).state == "quarantined"


def test_body_error_with_confirmed_cleanup_preserves_exact_error(
    c: ResourceCase,
) -> None:
    primary = ValueError("body failure")
    with pytest.raises(ValueError) as caught:
        with enter(c):
            raise primary
    assert caught.value is primary and inspect(c).state == "closed"


def test_physical_close_failure_attempts_emergency_abort(c: ResourceCase) -> None:
    with pytest.raises(BaseExceptionGroup):
        with enter(c):
            c.channels[0].engine.close_failure = OSError("native close failed")
    assert c.channels[0].aborts >= 1 and inspect(c).state == "quarantined"


def test_cleanup_clock_failure_cannot_skip_physical_close(c: ResourceCase) -> None:
    class FailedClock(SystemClock):
        def utcnow(self) -> datetime:
            raise OSError("clock failed")

    c.clock = FailedClock()
    with pytest.raises(BaseExceptionGroup):
        with enter(c):
            pass
    assert (
        c.channels[0].capture.termination is not None
        and c.channels[0].engine.state == "closed"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("resource_kind", "other"),
        ("provider_id", "other"),
        ("provider_version", "0"),
        ("attempt_id", "other"),
    ],
)
def test_invalid_resource_binding_rejected_before_effects(
    c: ResourceCase, field: str, value: str
) -> None:
    data = c.spec.model_dump()
    data["token"][field] = value
    with pytest.raises(ValidationError):
        BrowserResourceSpec.model_validate(data)
    assert not c.channels


@pytest.mark.parametrize("field", ["run_id", "owner_id", "attempt_id", "allocation_id"])
def test_wrong_operation_has_no_registration_or_launch(
    c: ResourceCase, field: str
) -> None:
    c.op = c.op.model_copy(update={field: "other"})
    with pytest.raises(OwnershipConflict):
        with enter(c):
            pass
    assert not c.channels and not list(c.journal._root.iterdir())


def test_foreign_action_allocation_rejected_but_original_cleanup_remains(
    c: ResourceCase,
) -> None:
    with enter(c) as browser:
        op = context(c.spec.token, "step").model_copy(update={"allocation_id": "other"})
        with pytest.raises(OwnershipConflict):
            browser.step(action(), op, control=c.controls.bind(op))
    assert inspect(c).state == "closed" and c.channels[0].engine.calls == [
        "start",
        "close",
    ]


def test_start_failure_before_child_preserves_known_no_start_and_error(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json
    from lab_generate_skill.ports.lifecycle import OperationControl

    original = ResourceChannel.start
    primary = OSError("spawn failed before child exists")

    def failed_start(self: ResourceChannel, control: OperationControl) -> None:
        self.start_error = primary
        original(self, control)

    monkeypatch.setattr(ResourceChannel, "start", failed_start)
    with pytest.raises(OSError) as caught:
        with enter(c):
            pytest.fail("startup failed")
    assert caught.value is primary
    record = inspect(c)
    assert (
        record.state == "closed"
        and c.channels[0].starts == 1
        and c.channels[0].process_id is None
    )
    assert (
        c.channels[0].capture.termination is not None
        and c.channels[0].capture.termination.state == "not_started"
    )
    ending = json.loads(c.evidence.read(record.events[-1].evidence[0]))
    assert ending["details"]["attempt"]["start_attempted"] is True
    assert ending["details"]["attempt"]["launcher_pid"] is None
    assert ending["details"]["primary"]["type_name"] == "OSError"


@pytest.mark.parametrize("schema", ["browser-initial-return/1", "observation/1"])
def test_start_publication_failure_retains_return_across_close(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch, schema: str
) -> None:
    import json
    from lab_generate_skill.domain.evidence import EvidenceMetadata
    from lab_generate_skill.ports.lifecycle import OperationControl

    original = c.evidence.put
    primary = OSError("initial evidence publication failed")

    def put(
        data: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        if metadata.content_schema == schema:
            raise primary
        return original(data, metadata, control=control)

    monkeypatch.setattr(c.evidence, "put", put)
    with pytest.raises(OSError) as caught:
        with enter(c):
            pytest.fail("initial publication failed")
    assert caught.value is primary
    assert inspect(c).state == "closed"
    assert c.channels[0].engine.calls == ["start", "close"]
    record = inspect(c)
    ending = json.loads(c.evidence.read(record.events[-1].evidence[0]))
    assert ending["details"]["startup_reply"]["phase"] == "start"
    assert ending["details"]["last_reply"]["phase"] == "close"
    assert ending["details"]["last_readout"]["observation"]["sequence"] == 0
    assert getattr(primary, "browser_resource_startup_reply").readout == getattr(
        primary, "browser_resource_readout"
    )
    assert getattr(primary, "browser_resource_readout").observation.sequence == 0


@pytest.mark.parametrize(
    "failure", ["initialize", "prepared_publication", "capture_publication"]
)
def test_early_owned_failure_retains_identity_and_never_grants_readiness(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    import json
    from lab_generate_skill.domain.evidence import EvidenceMetadata
    from lab_generate_skill.ports.lifecycle import OperationControl

    primary = OSError("controlled initialization boundary failure")
    original = c.evidence.put

    def put(
        data: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        if (
            failure == "prepared_publication"
            and metadata.content_schema == "browser-resource-prepared/1"
        ):
            raise primary
        if (
            failure == "capture_publication"
            and metadata.content_schema == "browser-step-raw/1"
        ):
            value = json.loads(data)
            if value.get("phase") == "worker-capture":
                raise primary
        return original(data, metadata, control=control)

    monkeypatch.setattr(c.evidence, "put", put)
    from browser_worker_fixtures import UnitBrowser

    def failed_start(*args: object, **kwargs: object) -> object:
        raise primary

    if failure == "initialize":
        monkeypatch.setattr(UnitBrowser, "start", failed_start)
    with pytest.raises((OSError, RuntimeError, BaseExceptionGroup)):
        with enter(c):
            assert failure == "capture_publication"
    ending = json.loads(c.evidence.read(inspect(c).events[-1].evidence[0]))["details"]
    attempt = ending["attempt"]
    assert attempt["prepared"] is not None and attempt["target"] is not None
    assert ending["configuration_reply"]["readout"] is None
    assert (
        attempt["started"] is None
        if failure != "capture_publication"
        else attempt["started"] is not None
    )
    if failure != "capture_publication":
        assert ("acquired" in [event.state for event in inspect(c).events]) == (
            failure == "initialize"
        )
        assert ending["last_readout"] is None
        assert ending["worker_capture_ref"] is not None
    else:
        assert inspect(c).state == "quarantined" and ending["cleanup_errors"]
    with pytest.raises(DispatchAlreadyCommitted):
        with enter(c):
            pytest.fail("original operation cannot repeat")


@pytest.mark.parametrize(
    "changed",
    [
        "old_spec",
        "old_provider",
        "old_attempt",
        "missing_prepared",
        "public_prepared",
        "foreign_prepared",
        "changed_installation",
    ],
)
def test_prepared_identity_cannot_be_upgraded_or_substituted(
    c: ResourceCase, changed: str
) -> None:
    import json
    from lab_generate_skill.domain.browser_resource import BrowserResourceAttempt

    if changed in ("old_spec", "old_provider"):
        data = c.spec.model_dump(mode="json")
        if changed == "old_spec":
            data["schema_version"] = "browser-resource-spec/2"
        else:
            data["token"]["provider_version"] = "1"
        with pytest.raises(ValidationError):
            BrowserResourceSpec.model_validate(data)
        assert not c.channels
        return
    with enter(c):
        pass
    data = json.loads(c.evidence.read(inspect(c).events[-1].evidence[0]))["details"][
        "attempt"
    ]
    assert (
        BrowserResourceAttempt.model_validate_json(json.dumps(data)).prepared_ref
        is not None
    )
    if changed == "old_attempt":
        data["schema_version"] = "browser-resource-attempt/2"
    elif changed == "missing_prepared":
        data["prepared"] = None
    elif changed == "public_prepared":
        data["prepared_ref"]["visibility"] = "public"
    elif changed == "foreign_prepared":
        data["prepared"]["owner_guard"]["worker"]["start_ticks"] += 1
    else:
        data["prepared"]["installed_sources"]["manifest_sha256"] = "f" * 64
    with pytest.raises(ValidationError):
        BrowserResourceAttempt.model_validate_json(json.dumps(data))
