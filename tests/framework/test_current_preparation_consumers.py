"""Real retained graphs and stage constructors, with explicitly unit-only rights.

Only process/storage admission is a test substitute. No original operation,
claim, journal, deadline or resource is updated; no native/model call occurs.
"""

import hashlib
import json
import os
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.plans.closed_source_protocol import decode_command
from lab_generate_skill.adapters.plans.closed_source_records import (
    ClosedSourceContexts,
    SupervisedClosedSourceContexts,
)
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.plans.stage_validation_source import (
    SupervisedStageValidationContexts,
)
from lab_generate_skill.adapters.plans.preparation_read import read_preparation_inputs
from lab_generate_skill.adapters.plans.baseline_read import read_baseline_inputs
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.storage.readonly_evidence import ReadOnlyEvidence
from lab_generate_skill.bootstrap.closed_source_read_bindings import (
    bind_closed_source_read,
)
from lab_generate_skill.domain.closed_source_read import ClosedSourceReadCommand
from lab_generate_skill.domain.claims import SourceClaimBinding
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from lab_generate_skill.domain.execution_task_source import ExecutionTaskSource
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.preparation_record import PreparationSelection
from lab_generate_skill.domain.preparation_read import PreparationReadRequest
from lab_generate_skill.domain.baseline_read import BaselineReadRequest
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from current_initial_adoption_fixtures import current_initial_case
from stage_validation_fixtures import UnitStageAuthority

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
C = W / "experiments/framework-combined-release-20261030-v1"


class UnitReadControls:
    def bind(self, operation):
        return DeadlineControl(120, "unit-retained-facts-only")


def retained_case(site):
    job, collected, package = (
        ("4981289", "4981344", "framework-admin-navigation-production-20261102-v1")
        if site == "admin"
        else ("4981290", "4981345", "framework-map-navigation42-production-20261102-v1")
    )
    root = W / "experiments" / package / ("production-" + job)
    receipt = json.loads(
        (
            C / ("held-stage-return-" + site + "-v3-" + collected) / "collection.json"
        ).read_bytes()
    )
    paths = [W / receipt[key]["path"] for key in ("member", "run", "session")]
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    session = EvidenceSessionSnapshot.model_validate_json(paths[2].read_bytes())
    command = decode_command((root / "source-read/last-request.json").read_bytes())
    store = ReadOnlyEvidence(
        root / "evidence", max_object_bytes=64 * 1024**2, reuse_within_proof=True
    )
    control = DeadlineControl(120, "retained-current-preparation")
    (row,) = [
        r for r in receipt["current_native_task_requests"] if r["action"] == "prepare"
    ]
    request_ref = EvidenceRef.model_validate(row["reference"])
    request = SiteTaskRequest.model_validate_json(store.read(request_ref, control))
    refs = {
        e.intent.reference
        for e in session.entries
        if e.intent.kind == "put" and e.intent.reference is not None
    }
    results = []
    environments = []
    sources = []
    for ref in refs:
        if ref.content_schema == "site-task-result/1":
            value = SiteTaskResult.model_validate_json(store.read(ref, control))
            if value.request_sha256 == request.digest:
                results.append(ref)
        elif ref.content_schema == "environment-baseline/1":
            value = EnvironmentBaseline.model_validate_json(store.read(ref, control))
            if value.scope.owner == session.binding.owner:
                environments.append(ref)
        elif ref.content_schema == "execution-task-source/2":
            value = ExecutionTaskSource.model_validate_json(store.read(ref, control))
            if value.run.owner == session.binding.owner:
                sources.append(value)
    (result_ref,) = results
    (environment_ref,) = environments
    (source,) = sources
    assert source.frozen_origin is not None
    selection = PreparationSelection(
        request_ref=request_ref, result_ref=result_ref, environment_ref=environment_ref
    )
    controls = UnitReadControls()
    historical = OperationContext(
        operation_id="readonly-unit-historical-facts",
        run_id=command.material.site.token.owner.run_id,
        owner_id=command.material.site.token.owner.owner_id,
        deadline=SystemClock().utcnow() + timedelta(seconds=120),
    )
    contexts = bind_closed_source_read(command.material).contexts(
        store, controls, historical
    )
    binding = SourceClaimBinding(
        scope_id=source.frozen_origin.validation.parent.record.binding.scope_id,
        run=source.run,
        task=source.task,
    )
    return SimpleNamespace(
        root=root,
        original=before,
        command=command,
        store=store,
        control=control,
        selected=PreparationReadRequest(
            selection=selection, operation=request.operation
        ),
        controls=controls,
        historical=historical,
        contexts=contexts,
        binding=binding,
        source=source,
    )


@pytest.mark.parametrize("site", ["admin", "map"])
def test_original_current_preparation_uses_real_stage_and_graph_consumers(site):
    c = retained_case(site)
    parent = UnitStageAuthority(c.source.frozen_origin.validation, c.binding)

    class UnitReadTransport(ClosedSourceReadTransport):
        def __init__(self):
            self.scope = SimpleNamespace(
                binding=c.command.scope.binding, config=c.command.scope.config
            )
            self.last_reply = None
            self.calls = 0
            self.revoke_after = False

        def check_current(self, control):
            control.checkpoint()

        def read(
            self,
            material,
            control,
            *,
            preparation_read=None,
            current_initial_owner=None,
        ):
            command = ClosedSourceReadCommand(
                schema_version="closed-source-read-command/3",
                scope=c.command.scope,
                workspace_root=c.command.workspace_root,
                material=material,
                kind="preparation_inputs",
                preparation_read=preparation_read,
                current_initial_owner=current_initial_owner,
            )
            assert decode_command(command.model_dump_json().encode()) == command
            self.calls += 1
            bodies = read_preparation_inputs(
                command.preparation_read,
                material,
                c.contexts,
                c.store,
                c.controls,
                control,
                c.historical,
                current_initial_owner=command.current_initial_owner,
            )
            self.last_reply = SimpleNamespace(preparation_bodies=bodies)
            if self.revoke_after:
                parent.denied = "parent"

    transport = UnitReadTransport()
    records = SupervisedStageValidationContexts(
        c.command.material,
        transport,
        c.controls,
        c.binding,
        c.source.frozen_origin,
        parent,
    )
    outer = ClosedSourceContexts(records, c.command.material.context_ref)
    body = outer.load_preparation_inputs(c.selected, c.control)
    assert body is not None and body.request == c.selected
    assert body.inputs.environment.scope.owner == c.binding.run.owner
    assert body.inputs.binding == c.binding.task
    assert body.inputs.environment.scope.owner != c.command.material.site.token.owner
    old = SupervisedClosedSourceContexts(c.command.material, transport, c.controls)
    with pytest.raises(OwnershipConflict, match="retag"):
        old.load_preparation_inputs(c.selected, c.control)
    with pytest.raises(OwnershipConflict, match="owner"):
        read_preparation_inputs(
            c.selected,
            c.command.material,
            c.contexts,
            c.store,
            c.controls,
            c.control,
            c.historical,
        )
    count = transport.calls
    parent.denied = "parent"
    with pytest.raises(OwnershipConflict):
        outer.load_preparation_inputs(c.selected, c.control)
    assert transport.calls == count
    parent.denied = ""
    transport.revoke_after = True
    with pytest.raises(OwnershipConflict):
        outer.load_preparation_inputs(c.selected, c.control)
    assert transport.calls == count + 1
    assert c.original == {
        name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in c.original
    }
    (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
        / ("current-preparation-" + site + ".json")
    ).write_text(
        json.dumps(
            dict(
                passed=True,
                original_job=c.binding.run.owner.job_id,
                current_owner_preserved=True,
                historical_source_unchanged=True,
                actual_stage_command_and_graph_consumers=True,
                process_storage_authority="unit-only",
                original_writes_native_model_claim_calls=0,
                runtime_grant=False,
            ),
            indent=2,
        )
        + "\n"
    )


def test_current_baseline_preserves_complete_graph_and_old_binding(tmp_path):
    c = current_initial_case(tmp_path / "baseline")
    source = c.original.parent.source.source
    material = SimpleNamespace(
        site=SimpleNamespace(token=SimpleNamespace(owner=source.run.owner)),
        browser=SimpleNamespace(
            configuration=SimpleNamespace(
                spec=SimpleNamespace(
                    task=SimpleNamespace(identity=source.task.identity)
                )
            )
        ),
        context_ref=source.source_context_receipt_ref,
    )
    selected = BaselineReadRequest(
        receipt=c.inputs.candidate, operation=c.receipt.operation
    )
    control = UnitReadControls().bind(selected.operation)
    original = OperationContext(
        operation_id="baseline-historical-binding",
        run_id=source.run.owner.run_id,
        owner_id=source.run.owner.owner_id,
        deadline=SystemClock().utcnow() + timedelta(seconds=120),
    )
    body = read_baseline_inputs(
        selected,
        material,
        c.original.contexts,
        c.records.store,
        control,
        original,
        current_initial_owner=c.original.binding.run.owner,
    )
    assert body.inputs == c.inputs.candidate_inputs
    with pytest.raises(OwnershipConflict, match="owner/task"):
        read_baseline_inputs(
            selected, material, c.original.contexts, c.records.store, control, original
        )


def test_current_initial_command_rejects_foreign_owner_and_implicit_historical_upgrade():
    c = retained_case("admin")
    value = dict(
        schema_version="closed-source-read-command/3",
        scope=c.command.scope,
        workspace_root=c.command.workspace_root,
        material=c.command.material,
        kind="preparation_inputs",
        preparation_read=c.selected,
        current_initial_owner=c.binding.run.owner,
    )
    assert ClosedSourceReadCommand(**value).current_initial_owner == c.binding.run.owner
    with pytest.raises(ValueError, match="exact current read owner"):
        ClosedSourceReadCommand(
            **{**value, "current_initial_owner": c.command.material.site.token.owner}
        )
    with pytest.raises(ValueError, match="Historical commands forbid"):
        ClosedSourceReadCommand(
            **{**value, "schema_version": "closed-source-read-command/1"}
        )
    with pytest.raises(ValueError, match="exact current read owner"):
        ClosedSourceReadCommand(
            **{k: v for k, v in value.items() if k != "current_initial_owner"}
        )
    raw = c.command.model_dump_json()
    assert (
        "current_initial_owner" not in raw and decode_command(raw.encode()) == c.command
    )
