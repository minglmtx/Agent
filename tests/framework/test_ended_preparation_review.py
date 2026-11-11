"""Consume both real retained failures; never dispatch or alter original records."""

import hashlib
import json
import os
from pathlib import Path
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.storage.readonly_evidence import ReadOnlyEvidence
from lab_generate_skill.adapters.plans.stage_parent import RetainedStageParentChecks
from lab_generate_skill.adapters.plans.prior_preparation_review import (
    load_ended_preparation,
)
from lab_generate_skill.adapters.plans.closed_stage_inputs import ClosedPriorStageInputs
from lab_generate_skill.domain.claims import SourceClaimRecord
from lab_generate_skill.domain.ended_stage_preparation import (
    EndedPreparationStageEvidence,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.execution_task_source import ExecutionTaskSource
from lab_generate_skill.domain.lifecycle import ResourceRecord
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.stage_validation_admission import (
    StageValidationAuthorization,
)
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
C = W / "experiments/framework-combined-release-20261030-v1"
CASES = (
    (
        "framework-admin-navigation-production-20261102-v1",
        "4980458",
        Path(os.environ["ENDED_PREPARATION_ADMIN_ACCOUNTING"]),
    ),
    (
        "framework-map-navigation42-production-20261102-v1",
        "4980459",
        C / "held-terminal-process-readback-v2-4981248/accounting.txt",
    ),
)


class RetainedReads:
    def __init__(self, root):
        self.original = ReadOnlyEvidence(
            root / "evidence", max_object_bytes=64 * 1024**2
        )
        self.objects = {}

    def add(self, raw, schema):
        ref = evidence_reference(
            raw,
            EvidenceMetadata(
                media_type="application/json",
                content_schema=schema,
                visibility="private",
                producer="ended-preparation-check",
            ),
        )
        self.objects[ref] = raw
        return ref

    def read(self, ref, control):
        control.checkpoint()
        raw = (
            self.objects[ref]
            if ref in self.objects
            else self.original.read(ref, control)
        )
        require_complete_bytes(ref, raw)
        return raw


class ReadControls:
    def __init__(self, gate):
        self.gate = gate

    def bind(self, operation):
        return self.gate


def retained(case):
    package, job, accounting = case
    root = W / "experiments" / package / ("production-" + job)
    gate = DeadlineControl(180, "ended-preparation-original-read")
    store = RetainedReads(root)
    (run_path,) = (root / "run").glob("*.run.json")
    snapshot = RunSnapshot.model_validate_json(run_path.read_bytes())
    _, attempts = snapshot.project()
    (task_plan_ref,) = [
        r
        for r in attempts[0].events[0].outputs
        if r.content_schema == "task-execution-plan/2"
    ]
    task_plan = TaskExecutionPlan.model_validate_json(store.read(task_plan_ref, gate))
    source_ref = task_plan.source_ref
    assert source_ref is not None
    source = ExecutionTaskSource.model_validate_json(store.read(source_ref, gate))
    claim_ref = source.intent.binding.claim_ref
    claim = SourceClaimRecord.model_validate_json(store.read(claim_ref, gate))
    assert source.frozen_origin is not None
    auth = StageValidationAuthorization.model_validate_json(
        store.read(source.frozen_origin.validation.authorization_ref, gate)
    )
    parent = RetainedStageParentChecks(
        source.frozen_origin,
        claim.binding,
        auth.authorization_id,
        store,
        ReadControls(gate),
    )
    resource_paths = {
        ResourceRecord.model_validate_json(p.read_bytes()).token.resource_kind: p
        for p in (root / "resources").glob("*.resource.json")
    }
    (session_path,) = (root / "sessions").glob("*.evidence-session.json")
    closure_data = json.loads(
        (
            C / "held-terminal-closure-readback-v2-4981051/closure/closure-data.json"
        ).read_bytes()
    )
    (closure,) = [r for r in closure_data["reports"] if r["original_job"] == job]
    (disposition,) = closure["original_dispositions"]
    from lab_generate_skill.domain.evidence import EvidenceRef

    inputs = EndedPreparationStageEvidence(
        claim_ref=claim_ref,
        source_ref=source_ref,
        run_ref=store.add(run_path.read_bytes(), "run-journal-snapshot/2"),
        actor_resource_ref=store.add(
            resource_paths["actor"].read_bytes(), "resource-record/2"
        ),
        site_resource_ref=store.add(
            resource_paths["site"].read_bytes(), "resource-record/2"
        ),
        session_ref=store.add(session_path.read_bytes(), "evidence-session-snapshot/3"),
        member_ref=store.add(
            (root / "member-result.json").read_bytes(), "retained-owned-member-result/1"
        ),
        accounting_ref=store.add(accounting.read_bytes(), "slurm-accounting-raw/1"),
        site_disposition_ref=EvidenceRef.model_validate(disposition["reference"]),
        process_observation_ref=(
            store.add(
                (
                    C / "held-terminal-process-readback-v2-4981248/observations.json"
                ).read_bytes(),
                "held-terminal-process-readback/1",
            )
            if job == "4980459"
            else None
        ),
    )
    paths = (
        run_path,
        session_path,
        *resource_paths.values(),
        root / "member-result.json",
    )
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    return store, parent, inputs, gate, before


def review(store, parent, inputs, gate):
    ref = store.add(inputs.model_dump_json().encode(), inputs.schema_version)
    return load_ended_preparation(parent, ref, gate)


@pytest.mark.parametrize("case", CASES)
def test_actual_original_preparation_graph(case):
    store, parent, inputs, gate, before = retained(case)
    result = review(store, parent, inputs, gate)
    assert (
        result.source.frozen_origin.parent_source_ref == parent.origin.parent_source_ref
    )
    assert result.resource.state in ("closed", "acquired")
    assert result.site.state == "closing"
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before} == before


@pytest.mark.parametrize("change", ("live_worker", "different_resource"))
def test_original_process_proof_must_match_and_end(change):
    store, parent, inputs, gate, _ = retained(CASES[1])
    proof = json.loads(store.read(inputs.process_observation_ref, gate))
    if change == "live_worker":
        proof["processes"][0]["observation"] = "same_incarnation"
    else:
        proof["actor_resource"]["sha256"] = "0" * 64
    replacement = store.add(
        json.dumps(proof).encode(), "held-terminal-process-readback/1"
    )
    selected = EndedPreparationStageEvidence.model_validate(
        inputs.model_copy(update={"process_observation_ref": replacement})
    )
    with pytest.raises(OwnershipConflict, match="process/cgroup inspection"):
        review(store, parent, selected, gate)


def test_original_private_site_cannot_be_substituted():
    store, parent, inputs, gate, _ = retained(CASES[0])
    disposition = json.loads(store.read(inputs.site_disposition_ref, gate))
    disposition["node_root"] += "-replacement"
    ref = store.add(json.dumps(disposition).encode(), "claimed-site-disposition/1")
    selected = EndedPreparationStageEvidence.model_validate(
        inputs.model_copy(update={"site_disposition_ref": ref})
    )
    with pytest.raises(OwnershipConflict, match="ending/isolation"):
        review(store, parent, selected, gate)


@pytest.mark.parametrize("case", CASES)
def test_explicit_schema_selection_and_shared_admin_publisher(case):
    from admin_production_prior_stage import ClosedPriorStageInputs as AdminInputs

    assert AdminInputs is ClosedPriorStageInputs
    store, parent, inputs, gate, _ = retained(case)
    ref = store.add(inputs.model_dump_json().encode(), inputs.schema_version)
    selected = AdminInputs((), (ref,))
    assert selected.authorization_schema == "task-stage-validation-authorization/4"
    original = json.loads(store.read(parent.origin.validation.authorization_ref, gate))
    original["closed_prior_stage_refs"] = [
        *original.get("closed_prior_stage_refs", []),
        ref.model_dump(mode="json"),
    ]
    original["schema_version"] = selected.authorization_schema
    assert (
        StageValidationAuthorization.model_validate_json(
            json.dumps(original)
        ).schema_version
        == selected.authorization_schema
    )
    for schema in (
        "task-stage-validation-authorization/2",
        "task-stage-validation-authorization/3",
    ):
        original["schema_version"] = schema
        with pytest.raises(ValidationError):
            StageValidationAuthorization.model_validate_json(json.dumps(original))


@pytest.mark.parametrize("site", ("admin", "map"))
def test_actual_thin_control_uses_exact_selected_schema(site, tmp_path):
    import importlib.util
    import os

    path = Path(os.environ["ENDED_PREPARATION_CONTROL"])
    spec = importlib.util.spec_from_file_location("ended_preparation_control", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = {
        "schema_version": "closed-prior-stage-publication/1",
        "closed_prior_stage_refs": [
            {"content_schema": "ended-preparation-stage-evidence/1"}
        ],
        "admission_or_model_grant": False,
    }
    selected = tmp_path / "selection.json"
    selected.write_text(json.dumps(data))
    digest = hashlib.sha256(selected.read_bytes()).hexdigest()
    proof = {
        "schema_version": "current-held-caller-qualification/1",
        "prior_inputs_sha256": digest,
        "authorization_schema": "task-stage-validation-authorization/4",
    }
    assert module.require_prior_selection(site, proof, selected, digest) == {
        "prior_stage_path": selected,
        "prior_stage_sha256": digest,
    }
    proof["authorization_schema"] = "task-stage-validation-authorization/3"
    with pytest.raises(ValueError, match="exact prior review schema"):
        module.require_prior_selection(site, proof, selected, digest)


def test_browser_summary_cannot_override_unstarted_proof():
    store, parent, inputs, gate, _ = retained(CASES[0])
    member = json.loads(store.read(inputs.member_ref, gate))
    member["execution_browser_record"] = {"state": "acquired"}
    ref = store.add(json.dumps(member).encode(), "retained-owned-member-result/1")
    selected = EndedPreparationStageEvidence.model_validate(
        inputs.model_copy(update={"member_ref": ref})
    )
    with pytest.raises(OwnershipConflict, match="active admission or task/model work"):
        review(store, parent, selected, gate)
