"""Explicit unit-only authorities over real plan/CAS/atomic claim storage."""

from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.adapters.ledger.source_stage_validation import (
    FileSourceStageValidations,
)
from lab_generate_skill.domain.claims import (
    SourceClaimBinding,
    SourceClaimRecord,
    SourceClaimReceipt,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.source_stage_validation import SourceStageValidation
from lab_generate_skill.ports.evidence import EvidenceStore
from claim_fixtures import Fixture, fixture, operation


class UnitStageAuthority:
    """Tests only; no user authorization, caller or native-state proof."""

    def __init__(
        self, validation: SourceStageValidation, binding: SourceClaimBinding
    ) -> None:
        self.validation, self.binding = validation, binding
        self.denied = ""
        self.parent_calls = self.create_calls = self.current_calls = 0

    def verify_parent(
        self, validation: SourceStageValidation, operation: OperationContext
    ) -> None:
        self.parent_calls += 1
        if self.denied == "parent" or validation != self.validation:
            raise OwnershipConflict("unit parent/authorization denied")

    def authorize_current(
        self,
        validation: SourceStageValidation,
        binding: SourceClaimBinding,
        plan: RunPlan,
        operation: OperationContext,
    ) -> None:
        self.create_calls += 1
        if (
            self.denied == "current"
            or binding != self.binding
            or plan.run_id != binding.run.owner.run_id
        ):
            raise OwnershipConflict("unit current creation denied")

    def verify_current(
        self,
        validation: SourceStageValidation,
        record: SourceClaimRecord,
        operation: OperationContext,
    ) -> None:
        self.current_calls += 1
        if self.denied == "current" or record.binding != self.binding:
            raise OwnershipConflict("unit current caller denied")


@dataclass
class StageFixture:
    original: Fixture
    parent: SourceClaimReceipt
    binding: SourceClaimBinding
    validation: SourceStageValidation
    authority: UnitStageAuthority

    @property
    def path(self) -> Path:
        return self.original.root / "claims" / self.validation.filename

    def ledger(self, store: EvidenceStore | None = None) -> FileSourceStageValidations:
        f = self.original
        return FileSourceStageValidations(
            f.root / "claims",
            f.binding.scope_id,
            f.controls,
            store or f.store,
            f.plans,
            self.authority,
            validation=self.validation,
        )


def stage_fixture(root: Path) -> StageFixture:
    f = fixture(root)
    parent = f.ledger().claim(f.binding, operation(f.binding))
    release = f.store.put(
        b'{"unit_only": "changed-release"}',
        EvidenceMetadata(
            media_type="application/json",
            content_schema="release-manifest/1",
            visibility="private",
            producer="unit-stage-fixture",
        ),
    )
    authorization = f.store.put(
        b'{"unit_only": "not-runtime-authorization"}',
        EvidenceMetadata(
            media_type="application/json",
            content_schema="task-stage-validation-authorization/1",
            visibility="private",
            producer="unit-stage-fixture",
        ),
    )
    plan = f.plans.load(f.binding.run, operation(f.binding))
    plan = RunPlan.model_validate(
        plan.model_copy(update={"run_id": "stage-run", "release_ref": release})
    )
    run = f.binding.run.model_copy(
        update={
            "owner": f.binding.run.owner.model_copy(
                update={"run_id": "stage-run", "job_id": "stage-job"}
            ),
            "release_ref": release,
            "submission_key": "stage-submission",
        }
    )
    binding = f.binding.model_copy(update={"run": run})
    ref = f.plans.publish(plan, operation(binding))
    binding = SourceClaimBinding.model_validate(
        binding.model_copy(update={"run": run.model_copy(update={"plan_ref": ref})})
    )
    validation = SourceStageValidation(
        parent=parent, target_release_ref=release, authorization_ref=authorization
    )
    return StageFixture(
        f, parent, binding, validation, UnitStageAuthority(validation, binding)
    )
