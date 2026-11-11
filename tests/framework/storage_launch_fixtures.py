"""Engineering publication/plan selection, never a formal acceptance receipt."""

from lab_generate_skill.domain.storage_launch import StorageLaunch
from lab_generate_skill.domain.storage_scope import StorageScope
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.release_activation import (
    ReleaseActivation,
    ReleaseDeployment,
    ReleaseSwitch,
)
from lab_generate_skill.domain.release_current import ReleaseCurrentSnapshot
from storage_scope_fixtures import scope
from test_run_plan import plan as unit_plan
from release_current_fixtures import ref, op


def selection(
    bound: StorageScope | None = None, plan: RunPlan | None = None
) -> tuple[StorageLaunch, ReleaseCurrentSnapshot]:
    bound = scope() if bound is None else bound
    if plan is None:
        plan = RunPlan.model_validate(
            unit_plan().model_copy(
                update={
                    "run_id": bound.run.owner.run_id,
                    "release_ref": bound.run.release_ref,
                    "purpose": "engineering",
                }
            )
        )
    plan_ref = evidence_reference(
        plan.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="run-plan/3",
            visibility="private",
            producer="run-plans-v1",
        ),
    )
    run = bound.run.model_copy(update={"plan_ref": plan_ref})
    claim = (
        bound.claim.model_copy(update={"run": run}) if bound.claim is not None else None
    )
    bound = StorageScope.model_validate(
        bound.model_copy(update={"run": run, "claim": claim})
    )
    activation = ReleaseActivation(
        release_id=bound.binding.release_id,
        manifest_ref=bound.run.release_ref,
        registry_ref=ref("task-registry/1"),
        acceptance_ref=ref("release-acceptance/1"),
    )
    launch = StorageLaunch(
        scope=bound,
        plan=plan,
        deployment=ReleaseDeployment(deployment_id="main", max_switches=5),
        activation=activation,
        revision=1,
    )
    snapshot = ReleaseCurrentSnapshot(
        deployment=launch.deployment,
        initialized_by=op(),
        switches=(
            ReleaseSwitch(
                expected_revision=0, activation=activation, operation=op("publish")
            ),
        ),
    )
    return launch, snapshot
