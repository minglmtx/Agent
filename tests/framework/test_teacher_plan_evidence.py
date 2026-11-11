"""Plan-only evidence I/O: exact bytes, bounded reads and uncertain commits.

The existing fixture constructs fake sources, counting and transport; these
tests never send a real model request or grant production source permission.
"""

from pathlib import Path
from typing import Any, cast

import pytest
from lab_generate_skill.adapters.plans.teacher_revision import (
    EvidenceTeacherRevisionPlans,
    publish_teacher_revision,
)
from lab_generate_skill.application.context_evidence import read_bytes
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OperationStopped
from lab_generate_skill.policies.evidence_bytes import (
    require_complete_read_bound,
    require_complete_bytes,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from evidence_control_fixtures import EvidenceFixtureStore
from teacher_revision_fixtures import revision_case
from test_slurm_commands import guard


class FaultPlanStore:
    def __init__(self, original: EvidenceFixtureStore, fault: str = "none") -> None:
        self.original, self.fault = original, fault
        self.reads = 0
        self.puts = 0
        self.error = OSError("injected original plan I/O acknowledgement loss")

    def read(self, ref: EvidenceRef, control: OperationControl) -> bytes:
        self.reads += 1
        raw = self.original.read(ref, control)
        if self.fault == "read_error":
            raise self.error
        if self.fault == "truncated":
            return raw[:-1]
        if self.fault == "corrupt":
            return bytes([raw[0] ^ 1]) + raw[1:]
        if self.fault == "wrong_type":
            return cast(bytes, bytearray(raw))
        return raw

    def put(
        self, raw: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        self.puts += 1
        ref = self.original.put(raw, metadata, control)
        if self.fault == "put_ack_loss":
            raise self.error
        if self.fault == "foreign_metadata":
            return ref.model_copy(update={"producer": "foreign-plan-producer"})
        return ref


class StopControl:
    def __init__(self, stop_at: int, error: BaseException) -> None:
        self.calls, self.stop_at, self.error = 0, stop_at, error

    def checkpoint(self) -> float:
        self.calls += 1
        if self.calls == self.stop_at:
            raise self.error
        return 60.0

    def wait(self, seconds: float) -> None:
        raise AssertionError("Plan evidence must not wait or retry")


def reference(raw: bytes) -> EvidenceRef:
    return evidence_reference(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="teacher-revision-plan/1",
            visibility="private",
            producer="unit-complete-evidence",
        ),
    )


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_complete_bytes_and_exact_read_bound(limit: int) -> None:
    raw = b"x" * limit
    ref = reference(raw)
    require_complete_read_bound(ref, limit)
    require_complete_bytes(ref, raw)
    with pytest.raises(EvidenceIntegrityError, match="read bound"):
        require_complete_read_bound(ref, limit - 1)


@pytest.mark.parametrize("limit", [None, False, True, "2", 0, -1, 1.5])
def test_invalid_bound_refuses_before_application_read(
    tmp_path: Path, limit: Any
) -> None:
    store = EvidenceFixtureStore(tmp_path)
    ref = reference(b"{}")
    # The explicit fixture below is never called for an invalid read bound.
    fault = FaultPlanStore(store)
    with pytest.raises(EvidenceIntegrityError, match="read bound"):
        read_bytes(fault, ref, limit, guard())
    assert fault.reads == fault.puts == 0


@pytest.mark.parametrize("raw", [b"", b"x", b"[}", None, "{}", bytearray(b"{}")])
def test_missing_truncated_wrong_digest_or_type_is_not_complete(raw: Any) -> None:
    with pytest.raises(EvidenceIntegrityError):
        require_complete_bytes(reference(b"{}"), raw)
    with pytest.raises(EvidenceIntegrityError):
        require_complete_read_bound(reference(b""), 1)


def test_plan_exact_publication_repeat_and_readonly_reuse(tmp_path: Path) -> None:
    c = revision_case(tmp_path / "case")
    store = FaultPlanStore(c.store)
    control = c.controls.bind(c.plan.send.operation)
    assert publish_teacher_revision(c.plan, store, control=control) == c.plan_ref
    assert publish_teacher_revision(c.plan, store, control=control) == c.plan_ref
    plans = EvidenceTeacherRevisionPlans(
        {c.plan.revision.request_id: c.plan_ref}, store
    )
    bound = plans.load_recorded(
        c.plan.revision.request_id, c.plan.send.operation, control=control
    )
    assert bound.plan == c.plan and bound.reference == c.plan_ref
    assert store.puts == 2 and len(c.transport.calls) == 0


@pytest.mark.parametrize("fault", ["truncated", "corrupt", "wrong_type", "read_error"])
def test_plan_bad_read_has_no_model_or_publication_retry(
    tmp_path: Path, fault: str
) -> None:
    c = revision_case(tmp_path / "case")
    store = FaultPlanStore(c.store, fault)
    plans = EvidenceTeacherRevisionPlans(
        {c.plan.revision.request_id: c.plan_ref}, store
    )
    with pytest.raises((EvidenceIntegrityError, OSError)):
        plans.load_recorded(
            c.plan.revision.request_id,
            c.plan.send.operation,
            control=c.controls.bind(c.plan.send.operation),
        )
    assert store.reads == 1 and store.puts == 0 and len(c.transport.calls) == 0


@pytest.mark.parametrize(
    "fault",
    [
        "put_ack_loss",
        "foreign_metadata",
        "truncated",
        "corrupt",
        "wrong_type",
        "read_error",
    ],
)
def test_plan_commit_or_readback_error_retains_exact_candidates_and_original_error(
    tmp_path: Path, fault: str
) -> None:
    c = revision_case(tmp_path / "case")
    store = FaultPlanStore(c.store, fault)
    with pytest.raises((EvidenceIntegrityError, OSError)) as caught:
        publish_teacher_revision(
            c.plan, store, control=c.controls.bind(c.plan.send.operation)
        )
    retained = getattr(caught.value, "teacher_plan_retained_refs")
    assert retained[0] == c.plan_ref
    assert len(retained) == (2 if fault == "foreign_metadata" else 1)
    if fault in ("put_ack_loss", "read_error"):
        assert caught.value is store.error
    assert store.puts == 1 and len(c.transport.calls) == 0
    # Inspect the original committed bytes. This is not another put or send.
    plans = EvidenceTeacherRevisionPlans(
        {c.plan.revision.request_id: retained[0]}, c.store
    )
    assert (
        plans.load_recorded(
            c.plan.revision.request_id,
            c.plan.send.operation,
            control=c.controls.bind(c.plan.send.operation),
        ).plan
        == c.plan
    )
    assert store.puts == 1


@pytest.mark.parametrize("stop_at", [1, 3, 7, 8])
@pytest.mark.parametrize("error_type", [OperationStopped, TimeoutError])
def test_cancel_or_timeout_before_effect_or_after_commit_keeps_candidate_no_retry(
    tmp_path: Path, stop_at: int, error_type: type[Exception]
) -> None:
    c = revision_case(tmp_path / "case")
    store = FaultPlanStore(c.store)
    original = (
        OperationStopped(
            "injected bounded plan evidence stop", c.plan.send.operation.operation_id
        )
        if error_type is OperationStopped
        else error_type("injected bounded plan evidence stop")
    )
    with pytest.raises(error_type) as caught:
        publish_teacher_revision(c.plan, store, control=StopControl(stop_at, original))
    assert caught.value is original
    assert getattr(caught.value, "teacher_plan_retained_refs") == (c.plan_ref,)
    assert store.puts == (0 if stop_at == 1 else 1)
    assert len(c.transport.calls) == 0
