"""Current RunPlan input proof through the existing fixed readonly worker.

The actual test reads retained failed4901844 data under a fresh reviewer only.
Original owner/claim/outcome are preserved. It grants no current source/run or
resource permission and does not replay its Actor or initialize a website.
"""

from pathlib import Path
import json
import pytest
from lab_generate_skill.domain.closed_source_read import (
    ClosedMapReadMaterial,
    ClosedSourceReadCommand,
)
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.adapters.plans.closed_source_records import (
    SupervisedRunPlanInputChecks,
)
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadFailure,
)
from lab_generate_skill.adapters.plans.closed_source_protocol import (
    decode_command,
    encode_command,
)
from closed_source_read_fixtures import actual_read_case
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from test_closed_source_read_protocol import E, original_material
from test_slurm_commands import guard
from registered_storage_fixtures import request
from lab_generate_skill.domain.evidence_read_scope import EvidenceReadScope


def retained_plan() -> tuple[ClosedMapReadMaterial, Path, RunPlan]:
    root = E / "production-4901844"
    raw = json.loads((root / "source-read/closed-declarations.json").read_bytes())
    material = ClosedMapReadMaterial.model_validate_json(json.dumps(raw))
    journal = json.loads(next((root / "run").glob("*.run.json")).read_bytes())
    reference = EvidenceRef.model_validate_json(
        json.dumps(journal["binding"]["plan_ref"])
    )
    from lab_generate_skill.adapters.storage.readonly_evidence import ReadOnlyEvidence

    store = ReadOnlyEvidence(root / "evidence", max_object_bytes=64 * 1024**2)
    plan = RunPlan.model_validate_json(store.read(reference, guard(30)))
    assert plan.run_id == material.site.token.owner.run_id
    return material, root / "evidence", plan


def test_actual_installed_full_plan_inputs_repeat_missing_and_no_regrant(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    material, root, plan = retained_plan()
    c = actual_read_case(tmp_path, installed_sources, retained=(material, root))
    before = {p.name: p.read_bytes() for p in (tmp_path / "sessions").iterdir()}
    original = None
    for _ in range(2):
        context = c.transport.read(material, guard(60), plan_inputs=plan)
        assert context.scope.owner == material.site.token.owner
        assert original is None or context == original
        original = context
        reply = c.transport.last_reply
        assert reply is not None and reply.plan_inputs_sha256 is not None
        assert reply.read_count >= len(plan.references())
        assert c.transport.last_request is not None
        assert decode_command(c.transport.last_request).plan_inputs == plan
    # A declared but absent input must still be physically checked every time.
    missing = plan.split_manifest_ref.model_copy(
        update={"sha256": "0" * 64, "uri": "cas://sha256/" + "0" * 64}
    )
    bad = plan.model_copy(update={"split_manifest_ref": missing})
    with pytest.raises(ClosedSourceReadFailure):
        c.transport.read(material, guard(60), plan_inputs=bad)
    assert c.transport.last_reply is not None
    assert c.transport.last_reply.context is None
    assert c.transport.last_reply.plan_inputs_sha256 is None
    assert c.current.store.state == "ready" and not c.transport.quarantined
    # Read-only old-owner proof cannot be injected as this reviewer's admission.
    checks = SupervisedRunPlanInputChecks(material, c.transport)
    with pytest.raises(OwnershipConflict):
        checks.verify_inputs(plan, c.op, guard(60))
    assert before == {p.name: p.read_bytes() for p in (tmp_path / "sessions").iterdir()}
    import os

    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    (output / "closed-plan-inputs-actual.json").write_text(
        json.dumps(
            {
                "historical_job": 4901844,
                "original_owner": plan.run_id,
                "direct_inputs": len(plan.references()),
                "timings": c.transport.timings,
                "scope": "retained read-only source and full direct plan inputs; no permission/replay/Actor",
                "old_namespace_written": False,
            },
            indent=2,
        )
        + "\n"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "plan_inputs"},
        {"kind": "plan_inputs", "plan_inputs": None},
        {"plan_inputs": None},
        {"kind": "plan_inputs", "plan_inputs": {}},
        {"kind": "plan_inputs", "plan_inputs": []},
    ],
)
def test_incomplete_or_wrong_plan_request_refuses_before_io(
    tmp_path: Path, change: dict[str, object]
) -> None:
    material, _ = original_material()
    original = request(tmp_path, create=True)
    scope = EvidenceReadScope(
        binding=original.binding,
        config=original.config,
        controller=original.controller,
        operation=original.operation,
        revision=0,
    )
    values = dict(
        scope=scope, material=material, workspace_root=str(E.parents[1]), kind="context"
    )
    values.update(change)
    with pytest.raises(ValueError):
        ClosedSourceReadCommand.model_validate(values)
