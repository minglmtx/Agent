"""Additional admission negatives over frozen v3, without upstream producers."""

from pathlib import Path
from datetime import timedelta
import pytest
from lab_generate_skill.adapters.ledger.stage_execution_authority import (
    StageExecutionClaimAuthority,
)
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_current_cgroup
from lab_generate_skill.adapters.storage.atomic_snapshot import AtomicSnapshotFile
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.claims import SourceClaimBinding, SourceClaimRecord
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.run_plan import RunPlan, ExecutionWorkload
from lab_generate_skill.domain.source_actor_policy import EngineeringActorPolicy
from lab_generate_skill.domain.source_stage_validation import SourceStageValidation
from construction_storage_fixtures import put
from stage_admission_fixtures import retained_case, operation_controls, stage_plan
from test_stage_execution_admission import RetainedContexts
from test_linux_cgroups import actual_slurm_execution
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "fault",
    [
        "old-policy",
        "old-window",
        "generations",
        "prior-validation",
        "prior-target",
        "expired",
    ],
)
def test_current_admission_rejects_changed_or_unresolved_inputs(
    tmp_path: Path, fault: str
) -> None:
    c = retained_case(tmp_path)
    op, controls, owner = operation_controls()
    execution, _ = actual_slurm_execution()
    controller = observe_current_cgroup(
        execution, current_process_identity(), guard(30)
    ).membership
    owner = owner.model_copy(update={"job_id": execution.job_id})
    target = put(c.store, {"isolated_admission_delta": True}, "release-manifest/1")
    run, binding = stage_plan(c, owner, target, corrected=fault != "old-policy")
    assert isinstance(run.workload, ExecutionWorkload)
    if fault in ("old-window", "generations"):
        policy = EngineeringActorPolicy.model_validate_json(
            c.store.read(run.workload.execution_policy_ref)
        )
        if fault == "old-window":
            cfg = ActorContextConfiguration.model_validate_json(
                c.store.read(policy.actor_context_ref)
            )
            cfg = ActorContextConfiguration.model_validate(
                cfg.model_copy(
                    update={
                        "profiles": tuple(
                            profile.model_copy(
                                update={"context_window": 32768, "input_limit": 28672}
                            )
                            for profile in cfg.profiles
                        )
                    }
                )
            )
            policy = EngineeringActorPolicy.model_validate(
                policy.model_copy(
                    update={"actor_context_ref": put(c.store, cfg, cfg.schema_version)}
                )
            )
            run = RunPlan.model_validate(
                run.model_copy(
                    update={
                        "workload": run.workload.model_copy(
                            update={
                                "execution_policy_ref": put(
                                    c.store, policy, policy.schema_version
                                )
                            }
                        )
                    }
                )
            )
        else:
            run = RunPlan.model_validate(
                run.model_copy(
                    update={
                        "resources": run.resources.model_copy(
                            update={
                                "max_actor_generations_per_attempt": policy.max_generations
                                + 1
                            }
                        )
                    }
                )
            )
        ref = c.store.put(
            run.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="run-plan/3",
                visibility="private",
                producer="run-plans-v1",
            ),
        )
        binding = SourceClaimBinding.model_validate(
            binding.model_copy(
                update={
                    "run": RunBinding.model_validate(
                        binding.run.model_copy(update={"plan_ref": ref})
                    )
                }
            )
        )
    parent = c.checker(binding, target, controls)
    root = c.shadow_claim_root(tmp_path / "claims")
    if fault in ("prior-validation", "prior-target"):
        legacy = SourceStageValidation.model_validate(
            parent.origin.validation.model_copy(
                update={"schema_version": "source-stage-validation/1"}
            )
        )
        if fault == "prior-target":
            legacy = SourceStageValidation.model_validate(
                parent.origin.validation.model_copy(
                    update={
                        "target_release_ref": put(
                            c.store, {"prior_target": True}, "release-manifest/1"
                        )
                    }
                )
            )
            prior_binding = SourceClaimBinding.model_validate(
                binding.model_copy(
                    update={
                        "run": binding.run.model_copy(
                            update={"release_ref": legacy.target_release_ref}
                        )
                    }
                )
            )
        else:
            prior_binding = binding
        record = SourceClaimRecord(binding=prior_binding, operation=op)
        with AtomicSnapshotFile(root, legacy.filename, max_bytes=128 * 1024).locked(
            guard(30)
        ) as transaction:
            transaction.write(record.model_dump_json().encode())
    before = {path.name: path.read_bytes() for path in root.iterdir()}
    authority = StageExecutionClaimAuthority(
        binding.scope_id,
        binding.run,
        binding.task,
        execution,
        controller,
        evidence=c.store,
        plans=EvidenceRunPlans(c.store, controls),
        contexts=RetainedContexts(parent),
        controls=controls,
        parent=parent,
        claim_root=root,
    )
    if fault == "expired":
        op = op.model_copy(update={"deadline": op.deadline - timedelta(days=1)})
    with pytest.raises((OwnershipConflict, OperationStopped)):
        authority.authorize_current(parent.origin.validation, binding, run, op)
    assert before == {path.name: path.read_bytes() for path in root.iterdir()}
