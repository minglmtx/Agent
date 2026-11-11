"""Actual fixed reader consumes the held Map source under an isolated new scope.

Current controller/storage are real Slurm. Validation/binding authorization is
explicitly unit-only: no production claim, native site, Actor or training grant.
"""

import json
import os
from pathlib import Path
import pytest
from lab_generate_skill.adapters.ledger.execution_claim_authority import (
    OriginalExecutionClaimAuthority,
)
from lab_generate_skill.adapters.ledger.source_stage_validation import (
    FileSourceStageValidations,
)
from lab_generate_skill.adapters.plans.closed_source_records import ClosedSourceContexts
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.adapters.plans.execution_task_source import (
    OriginalExecutionTaskSource,
)
from lab_generate_skill.adapters.plans.stage_validation_source import (
    SupervisedStageValidationContexts,
    SupervisedStageValidationSourceChecks,
)
from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.adapters.storage.atomic_snapshot import AtomicSnapshotFile
from lab_generate_skill.adapters.storage.readonly_evidence import ReadOnlyEvidence
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_process_cgroup
from lab_generate_skill.bootstrap.execution_task_source import (
    publish_execution_task_source,
)
from lab_generate_skill.domain.claims import (
    SourceClaimBinding,
    SourceClaimReceipt,
    SourceClaimRecord,
)
from lab_generate_skill.domain.closed_source_read import ClosedMapReadMaterial
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.execution_task_source import (
    ExecutionTaskSource,
    ExecutionTaskInputs,
)
from lab_generate_skill.domain.frozen_execution_origin import FrozenExecutionOrigin
from lab_generate_skill.domain.run_plan import RunPlan, ExecutionWorkload
from lab_generate_skill.domain.source_stage_validation import SourceStageValidation
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from closed_source_read_fixtures import actual_read_case
from construction_storage_fixtures import put
from evidence_control_fixtures import EvidenceFixtureStore
from execution_task_source_fixtures import UnitBindingAuthority
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from stage_validation_fixtures import UnitStageAuthority
from test_slurm_commands import guard


def test_installed_reader_keeps_held_map_source_and_current_validation_distinct(
    tmp_path: Path,
    installed_sources: InstalledFixture,
) -> None:
    w = Path("/anvme/workspace/r102bf10-lab-generate-skill")
    package = w / "experiments/framework-map-navigation42-production-20261102-v1"
    root = package / "production-4975122"
    original = ReadOnlyEvidence(root / "evidence", max_object_bytes=64 * 1024**2)
    index = json.loads(
        (
            w
            / "experiments/framework-combined-release-20261030-v1/finite-repair-results-4975123/map-4975122-outputs.json"
        ).read_bytes()
    )
    material = ClosedMapReadMaterial.model_validate_json(
        (root / "source-read/closed-declarations.json").read_bytes()
    )
    c = actual_read_case(
        tmp_path,
        installed_sources,
        fresh_cas=True,
        retained=(material, root / "evidence"),
    )
    store = EvidenceFixtureStore(tmp_path / "data")
    imported = 0
    refs: dict[str, list[EvidenceRef]] = {}
    for row in index["references"]:
        ref = EvidenceRef.model_validate(row["reference"])
        raw = original.read(ref, guard(30))
        imported += len(raw)
        metadata = EvidenceMetadata.model_validate(
            ref.model_dump(
                include={"media_type", "content_schema", "visibility", "producer"}
            )
        )
        assert store.put(raw, metadata) == ref
        refs.setdefault(ref.content_schema, []).append(ref)
    assert imported <= 16 * 1024**2
    assert (
        len(refs["execution-task-source/1"])
        == len(refs["task-execution-plan/2"])
        == len(refs["source-claim/1"])
        == 1
    )
    parent_source_ref = refs["execution-task-source/1"][0]
    parent_source = ExecutionTaskSource.model_validate_json(
        store.read(parent_source_ref)
    )
    old_task = TaskExecutionPlan.model_validate_json(
        store.read(refs["task-execution-plan/2"][0])
    )
    parent_claim = SourceClaimReceipt(
        record=SourceClaimRecord.model_validate_json(
            store.read(refs["source-claim/1"][0])
        ),
        reference=refs["source-claim/1"][0],
    )
    old_run = RunPlan.model_validate_json(store.read(parent_source.run.plan_ref))
    target = c.scope.config.installation.manifest_ref
    metadata = EvidenceMetadata.model_validate(
        target.model_dump(
            include={"media_type", "content_schema", "visibility", "producer"}
        )
    )
    assert (
        store.put(
            c.scope.config.installation.manifest.model_dump_json().encode(), metadata
        )
        == target
    )
    assert parent_source.intent.execution_inputs_ref is not None
    inputs = ExecutionTaskInputs.model_validate_json(
        store.read(parent_source.intent.execution_inputs_ref)
    )
    inputs = inputs.model_copy(update={"attempt_id": "isolated-validation-attempt"})
    input_ref = put(store, inputs, inputs.schema_version)
    assert isinstance(old_run.workload, ExecutionWorkload)
    run = RunPlan.model_validate(
        old_run.model_copy(
            update={
                "run_id": c.scope.binding.owner.run_id,
                "release_ref": target,
                "workload": old_run.workload.model_copy(
                    update={"task_inputs_ref": input_ref}
                ),
            }
        )
    )
    plans = EvidenceRunPlans(store, c.controls)
    bound = RunBinding(
        owner=c.scope.binding.owner,
        release_ref=target,
        plan_ref=plans.publish(run, c.op),
        submission_key="isolated-stage-proof",
    )
    binding = SourceClaimBinding(
        scope_id=parent_claim.record.binding.scope_id,
        run=bound,
        task=parent_source.task,
    )
    authorization = put(
        store, {"unit_only": True}, "task-stage-validation-authorization/1"
    )
    validation = SourceStageValidation(
        parent=parent_claim, target_release_ref=target, authorization_ref=authorization
    )
    authority = UnitStageAuthority(validation, binding)
    claim_root = tmp_path / "claims"
    claim_root.mkdir()
    with AtomicSnapshotFile(
        claim_root, binding.key.filename, max_bytes=128 * 1024
    ).locked(guard(30)) as transaction:
        transaction.write(parent_claim.record.model_dump_json().encode())
    parent_bytes = (claim_root / binding.key.filename).read_bytes()
    claims = FileSourceStageValidations(
        claim_root,
        binding.scope_id,
        c.controls,
        store,
        plans,
        authority,
        validation=validation,
    )
    claimed = claims.claim(binding, c.op)
    origin = FrozenExecutionOrigin(
        validation=validation, parent_source_ref=parent_source_ref
    )
    records = SupervisedStageValidationContexts(
        material, c.transport, c.controls, binding, origin, authority
    )
    contexts = ClosedSourceContexts(records, material.context_ref)
    owner = OriginalExecutionClaimAuthority(
        binding.scope_id,
        bound,
        binding.task,
        c.scope.execution,
        observe_process_cgroup(c.scope.execution, c.scope.writer, guard(30)).membership,
        evidence=store,
        plans=plans,
        contexts=contexts,
        controls=c.controls,
    )
    checks = SupervisedStageValidationSourceChecks(owner, records)
    reader = OriginalExecutionTaskSource(
        plans,
        claims,
        contexts,
        EvidenceTaskBindings(store, c.controls, UnitBindingAuthority()),
        store,
        source_checks=checks,
    )
    published = publish_execution_task_source(
        bound,
        claimed.reference,
        c.op,
        reader=reader,
        evidence=store,
        controls=c.controls,
        frozen_origin=origin,
    )
    task = TaskExecutionPlan.model_validate(
        old_task.model_copy(
            update={
                "intent": published.source.intent,
                "source_ref": published.source_ref,
                "read_operation": c.op,
                "operation": c.op.model_copy(
                    update={
                        "operation_id": c.op.operation_id + ".attempt",
                        "attempt_id": inputs.attempt_id,
                    }
                ),
                "evaluation": old_task.evaluation.model_copy(
                    update={"attempt_id": inputs.attempt_id}
                ),
            }
        )
    )
    with reader.task_scope(task):
        first = reader.load(task, c.op, guard(60))
        reply = c.transport.last_reply
        assert (
            reply is not None
            and reply.execution_source is not None
            and reply.execution_claim is not None
        )
        assert first.context.scope.owner == parent_source.run.owner
        assert first.source.run.owner == c.scope.binding.owner
        assert reader.load(task, c.op, guard(60)) == first
        assert c.transport.last_reply is reply
        authority.denied = "current"
        with pytest.raises(OwnershipConflict):
            reader.load(task, c.op, guard(60))
        authority.denied = ""
    with pytest.raises(OwnershipConflict):
        c.transport.require_current(material, c.op)
    authority.denied = "parent"
    with pytest.raises(OwnershipConflict):
        reader.load(task, c.op, guard(60))
    assert c.transport.last_reply is reply
    assert (claim_root / binding.key.filename).read_bytes() == parent_bytes
    assert (
        original.read(parent_source_ref, guard(30))
        == parent_source.model_dump_json().encode()
    )
    output = (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "frozen-source-installed.json"
    )
    output.write_text(
        json.dumps(
            dict(
                passed=True,
                original_job="4975122",
                imported_frozen_bytes=imported,
                source_scope_unchanged=True,
                current_scope_distinct=True,
                current_slurm_controller_checked=True,
                actual_fixed_worker_source2=True,
                same_call_immutable_source_reused=True,
                validation_authority="unit-only",
                production_claim_native_model_calls=0,
                runtime_grant=False,
            ),
            indent=2,
        )
        + "\n"
    )
