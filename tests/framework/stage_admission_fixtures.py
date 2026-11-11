"""Original held parent bytes in isolated CAS; never production claims or sites."""

import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.plans.stage_parent import RetainedStageParentChecks
from lab_generate_skill.adapters.storage.atomic_snapshot import AtomicSnapshotFile
from lab_generate_skill.adapters.storage.readonly_evidence import ReadOnlyEvidence
from lab_generate_skill.domain.actor_projection import AdaptiveObservationProjection
from lab_generate_skill.domain.claims import (
    SourceClaimBinding,
    SourceClaimReceipt,
    SourceClaimRecord,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.execution_task_source import (
    ExecutionTaskSource,
    ExecutionTaskInputs,
)
from lab_generate_skill.domain.frozen_execution_origin import FrozenExecutionOrigin
from lab_generate_skill.domain.lifecycle import OperationContext, ResourceOwner
from lab_generate_skill.domain.run_plan import RunPlan, ExecutionWorkload
from lab_generate_skill.domain.source_actor_policy import EngineeringActorPolicy
from lab_generate_skill.domain.source_stage_validation import SourceStageValidation
from lab_generate_skill.domain.stage_validation_admission import (
    StageParentEvidence,
    StageValidationAuthorization,
)
from lab_generate_skill.runtime.lifecycle import OperationGuards
from construction_storage_fixtures import put
from evidence_control_fixtures import EvidenceFixtureStore
from test_resource_journal import NoCancellation
from test_slurm_commands import guard

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
C = W / "experiments/framework-combined-release-20261030-v1"


@dataclass
class ParentCase:
    store: EvidenceFixtureStore
    refs: dict[str, list[EvidenceRef]]
    source: ExecutionTaskSource
    parent: SourceClaimReceipt
    evidence: StageParentEvidence
    root: Path
    original_root: Path

    def checker(
        self,
        binding: SourceClaimBinding,
        target: EvidenceRef,
        controls: OperationGuards,
        *,
        selected: StageParentEvidence | None = None,
        authorization_id: str = "isolated-stage-admission",
    ) -> RetainedStageParentChecks:
        auth = StageValidationAuthorization(
            authorization_id=authorization_id,
            binding=binding,
            parent_claim_ref=self.parent.reference,
            parent_source_ref=self.refs["execution-task-source/1"][0],
            parent_evidence=selected or self.evidence,
        )
        validation = SourceStageValidation(
            schema_version="source-stage-validation/2",
            parent=self.parent,
            target_release_ref=target,
            authorization_ref=put(self.store, auth, auth.schema_version),
        )
        origin = FrozenExecutionOrigin(
            validation=validation, parent_source_ref=auth.parent_source_ref
        )
        return RetainedStageParentChecks(
            origin, binding, authorization_id, self.store, controls
        )

    def shadow_claim_root(self, root: Path) -> Path:
        root.mkdir()
        with AtomicSnapshotFile(
            root, self.parent.record.binding.key.filename, max_bytes=128 * 1024
        ).locked(guard(30)) as transaction:
            transaction.write(self.parent.record.model_dump_json().encode())
        return root


def retained_case(
    root: Path, site: str = "map", store_root: Path | None = None
) -> ParentCase:
    job = "4975122" if site == "map" else "4975120"
    package = (
        "framework-map-navigation42-production-20261102-v1"
        if site == "map"
        else "framework-admin-navigation-production-20261102-v1"
    )
    original_root = W / "experiments" / package / ("production-" + job)
    original = ReadOnlyEvidence(
        original_root / "evidence", max_object_bytes=64 * 1024**2
    )
    index = json.loads(
        (
            C
            / ("finite-repair-results-" + str(int(job) + 1))
            / (site + "-" + job + "-outputs.json")
        ).read_bytes()
    )
    selected_root = store_root or root / "data"
    selected_root.mkdir(parents=True, exist_ok=True)
    store = EvidenceFixtureStore(selected_root)
    refs: dict[str, list[EvidenceRef]] = {}
    for row in index["references"]:
        ref = EvidenceRef.model_validate(row["reference"])
        metadata = EvidenceMetadata.model_validate(
            ref.model_dump(
                include={"media_type", "content_schema", "visibility", "producer"}
            )
        )
        assert store.put(original.read(ref, guard(30)), metadata) == ref
        refs.setdefault(ref.content_schema, []).append(ref)

    def raw(path: str, schema: str) -> EvidenceRef:
        return store.put(
            Path(path).read_bytes(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema=schema,
                visibility="private",
                producer="isolated-stage-parent-copy",
            ),
        )

    pins = index["original_file_pins"]
    evidence = StageParentEvidence(
        run_ref=raw(
            next(p for p in pins if p.endswith(".run.json")), "run-journal-snapshot/2"
        ),
        trace_ref=raw(
            next(p for p in pins if p.endswith(".trace.json")),
            "trace-journal-snapshot/1",
        ),
        initialized_ref=refs["initialized-task/1"][0],
        reset_refs=tuple(refs["reset-receipt/1"]),
        resource_refs=tuple(
            raw(p, "resource-record/2") for p in pins if p.endswith(".resource.json")
        ),
    )
    source = ExecutionTaskSource.model_validate_json(
        store.read(refs["execution-task-source/1"][0])
    )
    parent = SourceClaimReceipt(
        reference=refs["source-claim/1"][0],
        record=SourceClaimRecord.model_validate_json(
            store.read(refs["source-claim/1"][0])
        ),
    )
    return ParentCase(store, refs, source, parent, evidence, root, original_root)


def operation_controls() -> tuple[OperationContext, OperationGuards, ResourceOwner]:
    clock = SystemClock()
    controls = OperationGuards(clock, NoCancellation())
    owner = ResourceOwner(
        run_id="isolated-stage-run",
        owner_id="isolated-controller",
        job_id="isolated-job",
        worker_id="isolated-worker",
    )
    op = OperationContext(
        operation_id="isolated-admission",
        run_id=owner.run_id,
        owner_id=owner.owner_id,
        deadline=clock.utcnow() + timedelta(seconds=1200),
    )
    return op, controls, owner


def stage_plan(
    c: ParentCase, owner: ResourceOwner, target: EvidenceRef, *, corrected: bool = True
) -> tuple[RunPlan, SourceClaimBinding]:
    old = RunPlan.model_validate_json(c.store.read(c.source.run.plan_ref))
    assert isinstance(old.workload, ExecutionWorkload)
    inputs = ExecutionTaskInputs.model_validate_json(
        c.store.read(old.workload.task_inputs_ref)
    )
    inputs = inputs.model_copy(update={"attempt_id": "isolated-corrected-actor"})
    policy = EngineeringActorPolicy.model_validate_json(
        c.store.read(old.workload.execution_policy_ref)
    )
    assert isinstance(policy.actor_projection, AdaptiveObservationProjection)
    if corrected:
        read_policy = policy.actor_projection.read_policy.model_copy(
            update={
                "max_consecutive_invalid_proposals": 3,
                "max_identical_invalid_proposals": 3,
            }
        )
        policy = EngineeringActorPolicy.model_validate(
            policy.model_copy(
                update={
                    "actor_projection": policy.actor_projection.model_copy(
                        update={"read_policy": read_policy}
                    )
                }
            )
        )
    workload = old.workload.model_copy(
        update={
            "task_inputs_ref": put(c.store, inputs, inputs.schema_version),
            "execution_policy_ref": put(c.store, policy, policy.schema_version),
        }
    )
    run = RunPlan.model_validate(
        old.model_copy(
            update={"run_id": owner.run_id, "release_ref": target, "workload": workload}
        )
    )
    run_ref = c.store.put(
        run.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="run-plan/3",
            visibility="private",
            producer="run-plans-v1",
        ),
    )
    binding = SourceClaimBinding(
        scope_id=c.parent.record.binding.scope_id,
        run=RunBinding(
            owner=owner,
            release_ref=target,
            plan_ref=run_ref,
            submission_key="isolated-stage-proof",
        ),
        task=c.source.task,
    )
    return run, binding
