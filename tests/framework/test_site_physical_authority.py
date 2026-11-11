"""Independent site authority and actual existing registered resource integration."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any
import json
import pytest
from lab_generate_skill.adapters.sites.physical_authority import (
    ObservedSiteResourceAuthority,
)
from lab_generate_skill.adapters.sites import physical_authority as module
from lab_generate_skill.adapters.slurm.worker_evidence import WorkerStepEvidence
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.site_resource import SiteResourceAttempt
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.identity import TaskIdentity
from site_physical_authority_fixtures import PhysicalCase, physical_case, raw
from test_site_resource import inspect
from test_slurm_commands import guard


@pytest.fixture
def p(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PhysicalCase:
    return physical_case(tmp_path, monkeypatch)


def test_existing_registered_site_independent_admission_and_closed_journal(
    p: PhysicalCase,
) -> None:
    with p.enter():
        assert inspect(p.c).state == "acquired"
        assert p.authority.ready is not None
        assert len(p.ready_reads) == 2 and p.ready_reads[0] is not p.ready_reads[1]
    assert inspect(p.c).state == "closed"
    assert len(p.closed_reads) == 2 and p.closed_reads[0] is not p.closed_reads[1]
    assert p.c.authority.close_calls == 1
    assert len(p.authority.observations) == 2 and p.held[0].closes == 1
    ending = json.loads(p.c.evidence.read(inspect(p.c).events[-1].evidence[0]))
    assert len(ending["details"]["closure"]["evidence"]) == 2
    with pytest.raises(OwnershipConflict, match="replayed"):
        with p.enter():
            pytest.fail("replayed original worker")
    assert sum(c.starts for c in p.c.channels) == 1


@pytest.mark.parametrize("phase", ["spawn", "ready", "started", "closed"])
def test_original_source_denial_never_becomes_physical_permission(
    p: PhysicalCase, phase: str
) -> None:
    p.c.authority.deny = phase
    with pytest.raises((PermissionError, BaseExceptionGroup)):
        with p.enter():
            if phase != "closed":
                pytest.fail("source denial")
    if phase == "spawn":
        assert not p.c.channels and not p.authority.observations
    else:
        assert p.c.channels[0].capture.termination is not None
        assert p.held[0].closes == 1
        assert inspect(p.c).state == ("quarantined" if phase == "closed" else "closed")


@pytest.mark.parametrize("field", ["operation", "spec", "caller", "thread"])
def test_foreign_caller_or_scope_rejected_before_source_or_resource(
    p: PhysicalCase, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    spec, operation = p.c.spec, p.c.op
    if field == "operation":
        operation = operation.model_copy(update={"operation_id": "another"})
    elif field == "spec":
        spec = spec.model_copy(
            update={
                "configuration": spec.configuration.model_copy(
                    update={"apptainer": "/wrong"}
                )
            }
        )
    elif field == "caller":
        monkeypatch.setattr(
            module,
            "current_process_identity",
            lambda: spec.slurm.parent.writer.model_copy(
                update={"start_ticks": spec.slurm.parent.writer.start_ticks + 1}
            ),
        )
    with pytest.raises(OwnershipConflict):
        if field == "thread":
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(
                    p.authority.authorize_spawn, spec, operation, guard()
                ).result()
        else:
            p.authority.authorize_spawn(spec, operation, guard())
    assert not p.c.channels and not p.c.authority.calls


@pytest.mark.parametrize(
    "changes",
    [
        {"kernel": []},
        {"commands": None},
        {"error": {}},
        {"phase": "closed"},
        {"target": {}},
        {"schema_version": "site-step-raw/0"},
    ],
)
def test_incomplete_raw_refuses_before_independent_kernel_read(
    p: PhysicalCase, changes: dict[str, Any]
) -> None:
    with p.enter():
        ready = p.authority.ready
        assert ready is not None
        reference = raw(p.c, ready.controller.target, "ready", guard(), **changes)
        count = len(p.ready_reads)
        with pytest.raises(EvidenceIntegrityError):
            WorkerStepEvidence("site").require(
                p.c.evidence, reference, ready.controller.target, "ready", guard()
            )
        assert len(p.ready_reads) == count


@pytest.mark.parametrize(
    "which", ["empty", "wrong-json", "wrong-role", "wrong-type", "too-large"]
)
def test_raw_format_identity_and_bounds(p: PhysicalCase, which: str) -> None:
    with p.enter():
        ready = p.authority.ready
        assert ready is not None
        reference = p.c.evidence.put(
            b"" if which == "empty" else b"[]",
            EvidenceMetadata(
                media_type="application/json",
                content_schema="site-step-raw/1",
                visibility="private",
                producer="fixed-site-step-v1",
            ),
        )
        value: Any = reference
        if which == "wrong-role":
            value = reference.model_copy(update={"producer": "fixed-browser-step-v1"})
        elif which == "wrong-type":
            value = None
        elif which == "too-large":
            value = reference.model_copy(update={"size_bytes": 64 * 1024**2 + 1})
        with pytest.raises((ValueError, EvidenceIntegrityError)):
            WorkerStepEvidence("site").require(
                p.c.evidence, value, ready.controller.target, "ready", guard()
            )


def test_repeat_configure_start_ready_and_postclose_task_do_not_dispatch(
    p: PhysicalCase,
) -> None:
    with p.enter():
        for phase in ("configure", "start"):
            with pytest.raises(OwnershipConflict, match="one-shot"):
                p.authority.verify(p.c.spec.configuration, phase, p.c.op, guard())
        ready = p.authority.ready
        assert ready is not None
        with pytest.raises(OwnershipConflict, match="observation"):
            p.authority.verify_ready(p.c.spec, ready, p.c.op, guard())
    with pytest.raises(OwnershipConflict, match="admission"):
        p.authority.verify(p.c.spec.configuration, "configure", p.c.op, guard())
    assert p.c.authority.calls.count("start") == 1


@pytest.mark.parametrize(
    "failure",
    [
        "unconfirmed",
        "wrong-pid",
        "cleanup-error",
        "lost-source-close",
        "cancel-owner-check",
        "handle-close",
    ],
)
def test_partial_unknown_cancel_close_preserves_quarantine_and_original_handles(
    p: PhysicalCase, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    with pytest.raises(BaseExceptionGroup) as caught:
        with p.enter():
            if failure in ("unconfirmed", "wrong-pid", "cleanup-error"):
                original = p.authority.verify_closed

                def bad(*args: Any, **kwargs: Any) -> Any:
                    values = list(args)
                    termination = values[2]
                    if failure == "unconfirmed":
                        values[2] = replace(
                            termination, state="unconfirmed", returncode=None
                        )
                    elif failure == "wrong-pid":
                        values[2] = replace(
                            termination, process_id=termination.process_id + 1
                        )
                    else:
                        values[2] = replace(
                            termination, cleanup_errors=("original incomplete stop",)
                        )
                    return original(*values, **kwargs)

                monkeypatch.setattr(p.authority, "verify_closed", bad)
            elif failure == "lost-source-close":

                def lost(*args: Any, **kwargs: Any) -> Any:
                    raise OSError("original source closure acknowledgement lost")

                monkeypatch.setattr(p.c.authority, "verify_closed", lost)
            elif failure == "cancel-owner-check":
                original_owner = p.authority._owner

                def cancelled(control: Any) -> None:
                    if p.authority._close_attempted:
                        raise TimeoutError("cleanup bound expired")
                    original_owner(control)

                monkeypatch.setattr(p.authority, "_owner", cancelled)
            else:
                p.held[0].error = OSError("original pinned descriptor close lost")
    assert p.held[0].closes == 1
    assert inspect(p.c).state == "quarantined"
    assert p.c.channels[0].capture.termination is not None
    assert caught.value.exceptions


def test_actual_task_permission_is_delegated_and_cannot_outlive_original_site(
    p: PhysicalCase,
) -> None:
    config = p.c.spec.configuration
    request = SiteTaskRequest(
        task=TaskIdentity(
            source_task_id="source",
            task_id="task",
            split="train",
            site=config.site_id,
            family="unit",
            contract_version=1,
        ),
        binding_ref=config.token.recovery_ref.model_copy(
            update={"content_schema": "task-binding/1"}
        ),
        operation=p.c.op.model_copy(
            update={"attempt_id": "attempt", "operation_id": "snapshot"}
        ),
        action="snapshot",
        private_input="{}",
    )
    with p.enter():
        p.authority.verify_task(config, request, guard())
        assert p.c.authority.calls.count("task") == 1
    with pytest.raises(OwnershipConflict, match="inactive"):
        p.authority.verify_task(config, request, guard())
    assert p.c.authority.calls.count("task") == 1


def test_foreign_close_cannot_release_original_owner_handles(p: PhysicalCase) -> None:
    with p.enter():
        operation = p.c.op.model_copy(
            update={
                "mode": "cleanup",
                "parent_operation_id": "foreign",
                "operation_id": "foreign-close",
            }
        )
        with pytest.raises(OwnershipConflict, match="original operation"):
            p.authority.verify_closed(p.c.spec, None, None, None, operation, guard())  # type: ignore[arg-type]
        assert p.held[0].closes == 0 and not p.authority._close_attempted
    assert p.held[0].closes == 1 and inspect(p.c).state == "closed"


def test_bookkeeping_clock_failure_still_releases_observation_handles_without_false_closed(
    p: PhysicalCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = RuntimeError("original business operation failed")
    original_clock = p.c.clock.utcnow

    def failed_clock() -> Any:
        raise OSError("bookkeeping clock unavailable")

    with pytest.raises(BaseExceptionGroup) as caught:
        with p.enter():
            monkeypatch.setattr(p.c.clock, "utcnow", failed_clock)
            raise original
    assert caught.value.exceptions[0] is original
    assert p.c.channels[0].capture.termination is not None
    assert p.c.channels[0].capture.termination.state == "reaped"
    assert p.held[0].closes == 1 and p.authority._state.pin is None
    assert p.c.authority.close_calls == 0 and p.authority.closed is None
    monkeypatch.setattr(p.c.clock, "utcnow", original_clock)
    assert inspect(p.c).state == "acquired"
    assert len(p.closed_reads) == 1


def test_authority_requires_original_context_before_admission(p: PhysicalCase) -> None:
    with pytest.raises(OwnershipConflict, match="inactive"):
        p.authority.authorize_spawn(p.c.spec, p.c.op, guard())
    assert not p.c.channels and not p.c.authority.calls


@pytest.mark.parametrize("missing", ["source", "evidence"])
def test_no_default_source_or_evidence(p: PhysicalCase, missing: str) -> None:
    args: dict[str, Any] = {"source": p.c.authority, "evidence": p.c.evidence}
    args[missing] = None
    with pytest.raises(ValueError, match="mandatory"):
        ObservedSiteResourceAuthority(p.c.spec, p.c.op, **args)
