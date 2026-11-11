"""Declared metadata scope covers real controlled I/O; physical stop is separate."""

from pathlib import Path
from typing import Any
import json
import pytest
from lab_generate_skill.adapters.sites.resource import registered_site
from lab_generate_skill.adapters.sites.retained_resource import RetainedSiteResource
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.ports.lifecycle import OperationControl
from site_resource_fixtures import resource_case
from test_site_resource import inspect
from lab_generate_skill.adapters.sites.step import (
    observe_closed as original_observe_closed,
)
from lab_generate_skill.adapters.sites import step
from lab_generate_skill.domain.errors import OwnershipConflict
from test_slurm_commands import guard


def test_explicit_metadata_budget_reaches_original_cleanup_and_capture_without_changing_acquisition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = resource_case(tmp_path, monkeypatch)
    original_put = c.evidence.put
    budgets: list[float] = []

    def put(
        data: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        assert control is not None
        if (
            metadata.content_schema == "site-step-raw/1"
            and json.loads(data).get("phase") == "worker-capture"
        ):
            budgets.append(control.checkpoint())
            assert budgets[-1] > 60
        return original_put(data, metadata, control)

    monkeypatch.setattr(c.evidence, "put", put)
    held = RetainedSiteResource(
        c.spec,
        c.op,
        journal=c.journal,
        evidence=c.evidence,
        controls=c.controls,
        clock=c.clock,
        authority=c.authority,
        cleanup_seconds=120,
    )
    original_operation = c.op
    held.open(c.controls.bind(c.op))
    cleanup = c.op.cleanup("retained-explicit-close", now=c.clock.utcnow(), seconds=120)
    held.close(cleanup, c.controls.bind(cleanup))
    record = inspect(c)
    assert record.state == "closed" and c.op == original_operation
    final = record.events[-1].operation
    assert final.parent_operation_id is not None
    assert (final.deadline - c.clock.utcnow()).total_seconds() > 60
    assert len(budgets) == 1


@pytest.mark.parametrize("seconds", [None, True, 0, -1, 3601, "30", 1.5])
def test_bad_metadata_duration_cannot_register_or_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, seconds: Any
) -> None:
    c = resource_case(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        with registered_site(
            c.spec,
            c.op,
            journal=c.journal,
            evidence=c.evidence,
            controls=c.controls,
            clock=c.clock,
            authority=c.authority,
            cleanup_seconds=seconds,
        ):
            pytest.fail("Illegal metadata policy admitted")
    with pytest.raises(ValueError):
        RetainedSiteResource(
            c.spec,
            c.op,
            journal=c.journal,
            evidence=c.evidence,
            controls=c.controls,
            clock=c.clock,
            authority=c.authority,
            cleanup_seconds=seconds,
        )
    assert c.channels == []


def test_original_physical_stop_budget_never_becomes_step_evidence_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = resource_case(tmp_path, monkeypatch)
    original = step.observe_closed
    observed: list[tuple[float, float]] = []

    def close(*args: Any, metadata_control: OperationControl) -> Any:
        observed.append((args[-1].checkpoint(), metadata_control.checkpoint()))
        assert 0 < observed[-1][0] <= 15 and observed[-1][1] > 60
        return original(*args, metadata_control=metadata_control)

    monkeypatch.setattr(step, "observe_closed", close)
    with registered_site(
        c.spec,
        c.op,
        journal=c.journal,
        evidence=c.evidence,
        controls=c.controls,
        clock=c.clock,
        authority=c.authority,
        cleanup_seconds=120,
    ):
        pass
    assert inspect(c).state == "closed" and len(observed) == 1


@pytest.mark.parametrize("lost_ack", [False, True])
def test_unconfirmed_target_retains_error_with_metadata_scope_and_never_claims_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lost_ack: bool
) -> None:
    c = resource_case(tmp_path, monkeypatch)
    original = c.evidence.put
    seen: list[EvidenceRef] = []

    def put(
        raw: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        assert control is not None and control.checkpoint() > 60
        ref = original(raw, metadata, control)
        seen.append(ref)
        if lost_ack:
            raise OSError("Original closed-step diagnostic ACK lost")
        return ref

    monkeypatch.setattr(c.evidence, "put", put)
    expected = BaseExceptionGroup if lost_ack else OwnershipConflict
    with pytest.raises(expected) as caught:
        original_observe_closed(
            c.spec,
            step.SiteStepState(),
            None,
            c.evidence,
            guard(0.01),
            metadata_control=guard(120),
        )
    assert len(seen) == 1
    raw = json.loads(c.evidence.read(seen[0]))
    assert raw["error"] is not None and raw["target"] is None
    assert not tuple(c.journal._root.glob("*.resource.json"))
    if not lost_ack:
        assert getattr(caught.value, "site_step_evidence_ref") == seen[0]
