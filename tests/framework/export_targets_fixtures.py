"""Explicit nontraining export fixture over the original complete review chain."""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.application.review_run import review_run
from lab_generate_skill.application.export_targets import ExportDeps
from lab_generate_skill.bootstrap.export_targets import export_dependencies
from lab_generate_skill.domain.export import (
    ExportPlan,
    ExportScope,
    ExportSource,
    TrainingTargetQualification,
    ExportAdmission,
    DatasetLoadPlan,
)
from lab_generate_skill.domain.dataset import TrainingLabels
from lab_generate_skill.domain.export_material import ExportMaterial
from lab_generate_skill.domain.data_scope import SplitManifest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from construction_review_fixtures import ReviewCase, construction_review_case
from construction_storage_fixtures import put
from test_run_journal import command


class UnitExportAuthority:
    denied = False

    def verify_scope(
        self,
        plan: ExportPlan,
        scope: ExportScope,
        split: SplitManifest,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if self.denied:
            raise PermissionError("Unit export read/phase rights denied")
        assert scope.split_ref == plan.split_ref

    def admit(
        self,
        plan: ExportPlan,
        scope: ExportScope,
        source: ExportSource,
        material: ExportMaterial,
        control: OperationControl,
    ) -> ExportAdmission:
        control.checkpoint()
        return ExportAdmission(
            status="eligible" if plan.kind == "engineering_fixture" else "ineligible",
            reason_code=(
                "unit_fixture_only"
                if plan.kind == "engineering_fixture"
                else "unit_source_cannot_be_formal"
            ),
            evidence_refs=material.qualification.evidence_refs,
        )


class UnitChatTokenizer:
    def apply_chat_template(
        self,
        messages: list[dict[str, str]],
        *,
        tokenize: bool,
        add_generation_prompt: bool,
        enable_thinking: bool,
    ) -> list[int]:
        assert tokenize is True and enable_thinking is False
        text = "".join("<" + m["role"] + ">" + m["content"] for m in messages)
        text += "<assistant>" if add_generation_prompt else "</s>"
        return list(text.encode())


@dataclass
class ExportCase:
    review: ReviewCase
    scope: ExportScope
    scope_ref: EvidenceRef
    review_ref: EvidenceRef
    qualification_ref: EvidenceRef
    authority: UnitExportAuthority
    deps: ExportDeps

    def plan(self, name: str = "first") -> ExportPlan:
        read = self.review.plan("export-read-" + name)
        outer = command("export-original-" + name).model_copy(
            update={"deadline": datetime.now(timezone.utc) + timedelta(seconds=240)}
        )
        task = self.review.sealed.plan.task.identity
        return ExportPlan(
            export_id="export-" + name,
            kind="engineering_fixture",
            scope_ref=self.scope_ref,
            split_ref=self.scope.split_ref,
            release_ref=self.scope.release_ref,
            sources=(
                ExportSource(
                    example_id=task.task_id,
                    legacy_id=task.task_id,
                    review_ref=self.review_ref,
                    qualification_ref=self.qualification_ref,
                    review_read=read,
                ),
            ),
            seed=42,
            validation_ratio=0.05,
            operation=outer,
        )

    def load_plan(
        self, receipt_ref: EvidenceRef, name: str = "load"
    ) -> DatasetLoadPlan:
        exported = self.plan(name)
        return DatasetLoadPlan(
            export_receipt_ref=receipt_ref,
            expected_kind="engineering_fixture",
            purpose="inspect",
            sources=exported.sources,
            operation=exported.operation,
        )


def export_case(root: Path, monkeypatch: pytest.MonkeyPatch) -> ExportCase:
    c = construction_review_case(root, monkeypatch)
    read = c.plan("published-original-export-review")
    checked = review_run(read, c.deps(read))
    store = c.control.source.data.store
    review_ref = put(store, checked, "construction-review-receipt/1")
    proof = put(store, {"unit_nontraining_scope": True}, "unit-export-authorization/1")
    split_ref = c.sealed.plan.retrieval_scope.split_ref
    scope = ExportScope(
        scope_id="unit-export-scope",
        kind="engineering_fixture",
        release_ref=c.sealed.plan.run.release_ref,
        split_ref=split_ref,
        allowed_tasks=(c.sealed.plan.task.identity,),
        allowed_runs=(c.sealed.plan.run,),
        allowed_evaluation_scopes=("engineering",),
        evidence_refs=(proof,),
    )
    scope_ref = put(store, scope, "export-scope/1")
    qualification = TrainingTargetQualification(
        kind="engineering_fixture",
        run=c.sealed.plan.run,
        task=c.sealed.plan.task.identity,
        scope_ref=scope_ref,
        review_ref=review_ref,
        sealed_evidence_ref=c.source_ref,
        selected_evaluation_ref=checked.plan.selected_evaluation_ref,
        target_skill_ref=checked.selected_skill_ref,
        retrieval_ref=c.sealed.plan.retrieval_ref,
        labels=TrainingLabels(
            training_data=False,
            output_purpose="engineering",
            target_status="interface_verified",
            teacher_mode="fixture",
        ),
        evidence_refs=(proof,),
    )
    qualification_ref = put(store, qualification, "training-target-qualification/1")
    authority = UnitExportAuthority()
    data = c.control.source
    deps = export_dependencies(
        store,
        c.fifth.task.deps.controls,
        reviews=c.deps,
        retrieval=c.control.wire.review.source.retrieval,
        observations=data.review.native.observations,
        authority=authority,
    )
    return ExportCase(
        c, scope, scope_ref, review_ref, qualification_ref, authority, deps
    )
