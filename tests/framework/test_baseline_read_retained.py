"""Retained real producer baseline, fixed installed graph path, no task replay."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from lab_generate_skill.adapters.plans.closed_source_protocol import decode_command
from lab_generate_skill.adapters.plans.baseline_read import read_baseline_inputs
from lab_generate_skill.adapters.storage.readonly_evidence import ReadOnlyEvidence
from lab_generate_skill.bootstrap.closed_source_read_bindings import (
    bind_closed_source_read,
)
from lab_generate_skill.domain.baseline import BaselineReceipt
from lab_generate_skill.domain.baseline_read import BaselineReadRequest
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import InvalidTransition
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_resource_journal import NoCancellation
from test_slurm_commands import guard
from closed_source_read_fixtures import actual_read_case
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")


def test_failed_admin_baseline_uses_complete_original_producer_graph_without_replay() -> (
    None
):
    root = (
        W
        / "experiments/framework-admin-navigation-production-20261102-v1/production-4928366"
    )
    material = decode_command(
        (root / "source-read/last-request.json").read_bytes()
    ).material
    raw = (
        root
        / "evidence/blobs/e9ac138361eeb8e04571a5d6df641774f333c5b775f4bf64cc72e579443abd79"
    ).read_bytes()
    baseline = BaselineReceipt.model_validate_json(raw)
    evidence = ReadOnlyEvidence(
        root / "evidence", max_object_bytes=64 * 1024**2, reuse_within_proof=True
    )
    operation = OperationContext(
        operation_id="retained-baseline-failure-read",
        run_id=baseline.scope.owner.run_id,
        owner_id=baseline.scope.owner.owner_id,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=120),
    )
    controls = OperationGuards(SystemClock(), NoCancellation())
    contexts = bind_closed_source_read(material).contexts(evidence, controls, operation)
    body = read_baseline_inputs(
        BaselineReadRequest(receipt=baseline, operation=operation),
        material,
        contexts,
        evidence,
        guard(120),
        operation,
    )
    assert body.inputs.prepared.scope == baseline.scope and baseline.status == "ready"
    assert evidence.body_read_count == len(evidence.unique_objects)
    assert (
        root
        / "evidence/blobs/e9ac138361eeb8e04571a5d6df641774f333c5b775f4bf64cc72e579443abd79"
    ).read_bytes() == raw


def test_installed_baseline_graph_proof_is_bounded_exact_and_revocable(
    tmp_path: Path,
    installed_sources: InstalledFixture,
) -> None:
    c = actual_read_case(tmp_path, installed_sources)
    context = c.transport.read(c.material, c.controls.bind(c.op))
    evidence = ReadOnlyEvidence(
        Path(c.scope.config.evidence_root), max_object_bytes=64 * 1024**2
    )
    baseline = BaselineReceipt.model_validate_json(
        evidence.read(context.baseline_ref, guard(30))
    )
    op = OperationContext(
        operation_id="installed-baseline-proof",
        run_id=baseline.scope.owner.run_id,
        owner_id=baseline.scope.owner.owner_id,
        deadline=c.op.deadline,
    )
    selected = BaselineReadRequest(receipt=baseline, operation=op)
    c.transport.read(c.material, c.controls.bind(c.op), baseline_read=selected)
    reply = c.transport.last_reply
    assert reply is not None and reply.baseline_bodies is not None
    assert reply.schema_version == "closed-source-read-reply/5"
    assert (
        reply.baseline_bodies.request == selected
        and reply.baseline_bodies.inputs.prepared.scope == baseline.scope
    )
    assert reply.body_read_count == reply.unique_objects
    count = len(c.transport.timings)
    c.current.admission.stop_new_io()
    with pytest.raises(InvalidTransition):
        c.transport.read(c.material, c.controls.bind(c.op), baseline_read=selected)
    assert len(c.transport.timings) == count
