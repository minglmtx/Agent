"""Current source graph with explicit unit kernel premises; old actual/1 refuses.

No actual website/model/Actor calls. Production never installs the kernel premise.
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import re
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.slurm.worker_evidence import WorkerStepEvidence
from lab_generate_skill.bootstrap.map_closed_source import closed_map_source_contexts
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.slurm_step import SlurmStepTarget
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards
from map_closed_source_fixtures import original_closed_source
from map_registered_worker_fixtures import RegisteredMapCase
from map_navigation_source_fixtures import source_combination
import map_navigation_source_fixtures as source_fixtures
from map_navigation_fixtures import navigation_case
from source_review_records import ReadOnlyEvidence
from test_resource_journal import NoCancellation
from test_site_resource import inspect
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
ORIGINAL = (
    W
    / "experiments/framework-map-navigation-actual-batch-20261101-v1/actual-member-4872207"
)


def test_original_closed_source_rechecks_actual_files_and_readonly_boundary() -> None:
    # The prior failed fixture mixed old live /1 with the current /2 producer.
    # Preserve that exact incompatible input as a refusal; no origin synthesis.
    actor = json.loads((ORIGINAL / "map-actor-native/facts.json").read_bytes())
    store = ReadOnlyEvidence(ORIGINAL / "map-actor-native/resource/evidence")
    with pytest.raises(ValueError, match="map-navigation-worker-inputs/1"):
        original_closed_source(Path(actor["site_facts_path"]), store, guard(30))


def unit_kernel_envelope(
    self: WorkerStepEvidence,
    store: EvidenceReader,
    reference: EvidenceRef,
    target: SlurmStepTarget,
    phase: str,
    control: OperationControl,
) -> None:
    assert phase == "closed" and reference.content_schema == "synthetic-closure-proof/1"
    raw = json.loads(store.read(reference, control))
    assert raw["synthetic_kernel"] and raw["target"] == target.model_dump(mode="json")
    control.checkpoint()


@pytest.mark.parametrize("source_id", ["125732d3658ab4daee02", "218b9e1f3bbafdd12bfa"])
def test_current_closed_source_graph_rechecks_full_initial_reset_and_readonly_scope(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_id: str,
) -> None:
    original = navigation_case(source_id)
    heading = re.sub(
        r"\\(.)", r"\1", original.native["completion"]["heading_regex"][1:-1]
    )
    # This old source helper's MEMBERS is explicitly the terminal-page double
    # injection point. Keep the current42 input bytes/scope unchanged.
    monkeypatch.setattr(
        source_fixtures,
        "MEMBERS",
        ((source_id, original.native["control_target_path"], heading),),
    )
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=source_id)
    try:
        facts = source_combination(c, monkeypatch)
        facts["resource_record"] = inspect(c.resource).model_dump(mode="json")
        fact_path = c.workspace / "closed-source-unit-facts.json"
        fact_path.write_text(json.dumps(facts))
        store = ReadOnlyEvidence(c.workspace / "evidence")
        controls = OperationGuards(SystemClock(), NoCancellation())
        op = OperationContext(
            operation_id="closed-source-reader",
            run_id=c.scope.owner.run_id,
            owner_id=c.scope.owner.owner_id,
            deadline=datetime.now(timezone.utc) + timedelta(seconds=120),
        )
        d = original_closed_source(fact_path, store, controls.bind(op))
        # The production boundary rejects these synthetic closure schemas.
        with pytest.raises(EvidenceIntegrityError, match="role-bound worker raw"):
            closed_map_source_contexts(d, store, controls, op)
        # Explicit kernel premise for software graph/identity coverage only.
        monkeypatch.setattr(WorkerStepEvidence, "require", unit_kernel_envelope)
        reader = closed_map_source_contexts(d, store, controls, op)
        receipt = reader.load_context(d.context_ref, op)
        assert receipt.scope == c.scope
        assert reader.load_context(d.context_ref, op) == receipt
        for call in (
            reader.publish_context,
            reader.publish_equivalence,
            reader.load_equivalence,
        ):
            with pytest.raises(PermissionError):
                call()
        with pytest.raises(OwnershipConflict):
            reader.load_context(d.environment_ref, op)
        with pytest.raises(OwnershipConflict):
            reader.load_context(
                d.context_ref, op.model_copy(update={"owner_id": "foreign"})
            )
        invalids: tuple[Any, ...] = (None, "", {}, [])
        for wrong in invalids:
            with pytest.raises(TypeError):
                closed_map_source_contexts(wrong, store, controls, op)
        altered = d.site_record.model_copy(update={"events": d.site_record.events[:-1]})
        with pytest.raises((EvidenceIntegrityError, ValueError)):
            closed_map_source_contexts(
                replace(d, site_record=altered), store, controls, op
            )
    finally:
        c.close_sockets()
