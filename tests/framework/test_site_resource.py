"""Persistent worker acquisition before native effects, truthful independent close."""

from contextlib import AbstractContextManager
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
import json
import uuid
import pytest
from lab_generate_skill.adapters.sites.resource import registered_site, RegisteredSite
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
)
from lab_generate_skill.domain.lifecycle import ResourceRecord
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from site_resource_fixtures import Case, resource_case


def enter(c: Case) -> AbstractContextManager[RegisteredSite]:
    return registered_site(
        c.spec,
        c.op,
        journal=c.journal,
        evidence=c.evidence,
        controls=c.controls,
        clock=c.clock,
        authority=c.authority,
    )


def inspect(c: Case) -> ResourceRecord:
    return c.journal.read(
        c.spec.token,
        c.op.cleanup(
            "inspect-" + uuid.uuid4().hex, now=datetime.now(timezone.utc), seconds=30
        ),
    )


@pytest.fixture
def c(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Case:
    return resource_case(tmp_path, monkeypatch)


def test_registered_identity_before_site_effects_and_once_only(c: Case) -> None:
    with enter(c) as started:
        assert inspect(c).state == "acquired"
        assert started.site.instance.files == c.spec.configuration.files
        assert (
            json.loads(c.evidence.read(started.site.evidence))["details"]["started"][
                "endpoint"
            ]
            == started.site.instance.endpoint
        )
    assert [e.state for e in inspect(c).events] == [
        "registered",
        "acquiring",
        "acquired",
        "closing",
        "closed",
    ]
    assert c.channels[0].engine.calls == ["start", "stop"]
    with pytest.raises(DispatchAlreadyCommitted):
        with enter(c):
            pytest.fail("repeated launch")
    assert sum(ch.starts for ch in c.channels) == 1


@pytest.mark.parametrize("denied", ["spawn", "ready", "started", "closed"])
def test_mandatory_permissions_before_use(c: Case, denied: str) -> None:
    c.authority.deny = denied
    with pytest.raises((PermissionError, BaseExceptionGroup)):
        with enter(c):
            pass
    if denied == "spawn":
        assert not c.channels and not list(c.journal._root.iterdir())
    else:
        assert inspect(c).state == ("quarantined" if denied == "closed" else "closed")
        assert c.channels[0].capture.termination is not None
        if denied == "ready":
            assert c.channels[0].engine.calls == []


def test_lost_begin_ack_never_spawns_or_closes_another(
    c: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = c.journal.begin_acquire

    def lost(*args: Any, **kwargs: Any) -> ResourceRecord:
        original(*args, **kwargs)
        raise OSError("lost begin ack")

    monkeypatch.setattr(c.journal, "begin_acquire", lost)
    with pytest.raises(OSError):
        with enter(c):
            pytest.fail("unknown permission")
    assert inspect(c).state == "acquiring"
    assert (
        c.channels[0].starts == c.channels[0].aborts == 0
        and c.authority.close_calls == 0
    )


@pytest.mark.parametrize("state", ["acquired", "closing", "closed"])
@pytest.mark.parametrize("committed", [False, True])
def test_commit_boundaries_never_skip_physical_close(
    c: Case, monkeypatch: pytest.MonkeyPatch, state: str, committed: bool
) -> None:
    original = c.journal.advance
    attempted = False

    def failing(*args: Any, **kwargs: Any) -> ResourceRecord:
        nonlocal attempted
        if args[1] == state and not attempted:
            attempted = True
            if committed:
                original(*args, **kwargs)
            raise OSError("injected journal commit failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(c.journal, "advance", failing)
    with pytest.raises((OSError, BaseExceptionGroup)) as caught:
        with enter(c):
            pass
    assert c.channels[0].capture.termination is not None
    assert c.channels[0].capture.termination.state == "reaped"
    if state == "acquired":
        assert c.channels[0].engine.calls == []
    assert c.channels[0].starts == 1
    expected = {
        ("acquired", False): "closed",
        ("acquired", True): "closed",
        ("closing", False): "acquired",
        ("closing", True): "closing",
        ("closed", False): "closing",
        ("closed", True): "closed",
    }
    assert inspect(c).state == expected[state, committed]
    ref = getattr(caught.value, "site_resource_ending_ref")
    assert ref is not None
    ending = json.loads(c.evidence.read(ref))
    assert ending["state"] == ("quarantined" if state == "closing" else "closed")
    assert ending["details"]["worker_capture_ref"] is not None
    assert getattr(caught.value, "site_resource_attempt").spawn_attempted


def test_original_body_error_with_clean_close_is_not_replaced(c: Case) -> None:
    primary = RuntimeError("original task failed")
    with pytest.raises(RuntimeError) as caught:
        with enter(c):
            raise primary
    assert caught.value is primary and inspect(c).state == "closed"


def test_primary_and_unconfirmed_cleanup_both_survive(c: Case) -> None:
    primary = RuntimeError("original task failed")
    c.authority.deny = "closed"
    with pytest.raises(BaseExceptionGroup) as caught:
        with enter(c):
            raise primary
    assert caught.value.exceptions[0] is primary
    assert inspect(c).state == "quarantined"


@pytest.mark.parametrize(
    "field", ["run_id", "owner_id", "allocation_id", "recovery_ref"]
)
def test_wrong_operation_never_registers_or_launches(c: Case, field: str) -> None:
    c.op = c.op.model_copy(
        update={field: None if field == "recovery_ref" else "foreign"}
    )
    with pytest.raises((ValueError, OwnershipConflict)):
        with enter(c):
            pass
    assert not c.channels and not list(c.journal._root.iterdir())


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "site-resource-spec/0"),
        ("configuration", None),
        ("slurm", {}),
        ("slurm", None),
    ],
)
def test_invalid_spec_rejected(c: Case, field: str, value: Any) -> None:
    data = c.spec.model_dump()
    data[field] = value
    with pytest.raises(ValueError):
        SiteResourceSpec.model_validate(data)
    assert not c.channels


@pytest.mark.parametrize("committed", [False, True])
def test_worker_capture_publication_failure_retains_candidate_and_stops(
    c: Case, monkeypatch: pytest.MonkeyPatch, committed: bool
) -> None:
    original = c.evidence.put

    def fail(data: bytes, *args: Any, **kwargs: Any) -> Any:
        payload = json.loads(data)
        if (
            payload.get("schema_version") == "site-step-raw/1"
            and payload.get("phase") == "worker-capture"
        ):
            if committed:
                original(data, *args, **kwargs)
            raise OSError("capture publication unknown")
        return original(data, *args, **kwargs)

    monkeypatch.setattr(c.evidence, "put", fail)
    with pytest.raises(BaseExceptionGroup) as caught:
        with enter(c):
            pass
    assert inspect(c).state == "quarantined"
    assert (
        c.channels[0].capture.termination is not None
        and c.channels[0].capture.termination.state == "reaped"
    )
    ending = json.loads(
        c.evidence.read(getattr(caught.value, "site_resource_ending_ref"))
    )
    assert ending["details"]["worker_capture_ref"] is None
    assert len(ending["details"]["step_diagnostic_candidates"]) == 1


def test_cleanup_clock_failure_does_not_skip_original_process(
    c: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken() -> Any:
        raise OSError("bookkeeping clock failed")

    with pytest.raises(BaseExceptionGroup):
        with monkeypatch.context() as scope:
            with enter(c):
                scope.setattr(c.clock, "utcnow", broken)
    assert (
        c.channels[0].capture.termination is not None
        and c.channels[0].capture.termination.state == "reaped"
    )
    assert inspect(c).state == "acquired"
    assert c.channels[0].engine.calls == ["start", "stop"]


@pytest.mark.parametrize(
    "changed", ["token", "operation", "public_proof", "missing_proof"]
)
def test_closure_cannot_replace_original_binding_or_proof(
    c: Case, monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    original = c.authority.verify_closed

    def counterfeit(*args: Any, **kwargs: Any) -> Any:
        value = original(*args, **kwargs)
        if changed == "token":
            return value.model_copy(
                update={
                    "token": value.token.model_copy(
                        update={"expected_resource_id": "foreign"}
                    )
                }
            )
        if changed == "operation":
            return value.model_copy(update={"operation_id": "foreign"})
        proof = value.evidence[0]
        if changed == "public_proof":
            proof = proof.model_copy(update={"visibility": "public"})
        else:
            proof = proof.model_copy(
                update={"sha256": "0" * 64, "uri": "cas://sha256/" + "0" * 64}
            )
        return value.model_copy(update={"evidence": (proof,)})

    monkeypatch.setattr(c.authority, "verify_closed", counterfeit)
    with pytest.raises(BaseExceptionGroup):
        with enter(c):
            pass
    assert inspect(c).state == "quarantined"
    assert (
        c.channels[0].capture.termination is not None
        and c.channels[0].capture.termination.state == "reaped"
    )
