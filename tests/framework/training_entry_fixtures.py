"""Synthetic training contracts, never an actual qualified source or SFT sample.

Positive unit tests substitute only the dataset reader and model leaf. They do
not relabel/publish any engineering example, execute a model or prove formal
source/phase admission. A separate negative uses the original export reader.
"""

from collections.abc import Iterator
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.application.export_targets import export_targets
from lab_generate_skill.domain.dataset import (
    TrainingExample,
    TrainingLabels,
    SFTMessage,
    DatasetManifest,
    DatasetItem,
)
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.domain.export import (
    ExportReceipt,
    ExportDecision,
    DatasetLoadPlan,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.release import ReleaseArtifact, ReleaseFile
from lab_generate_skill.domain.training import (
    TrainingPlan,
    TrainingSpec,
    TrainingRunResult,
)
from lab_generate_skill.policies.dataset_manifest import (
    export_metadata,
    example_reference,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from export_targets_fixtures import ExportCase, export_case


def ref(name: str, schema: str, visibility: str = "private") -> EvidenceRef:
    return evidence_reference(
        name.encode(),
        EvidenceMetadata.model_validate(
            dict(
                media_type="application/json",
                content_schema=schema,
                visibility=visibility,
                producer="unit-sft-contract-only",
            )
        ),
    )


def contract_data() -> LoadedDataset:
    labels = TrainingLabels(
        training_data=True,
        output_purpose="training",
        target_status="environment_verified",
        teacher_mode="authorized_api",
    )
    rows = []
    for letter in ("A", "B"):
        ident = "unit-sft-contract-" + letter
        row = TrainingExample(
            kind="formal",
            example_id=ident,
            legacy_id=ident,
            task=TaskIdentity(
                task_id=ident,
                source_task_id=ident,
                split="train",
                site="map",
                family="unit-contract-only",
                contract_version=1,
            ),
            goal_group_id="unit-goal-" + letter,
            group_goal="unit synthetic goal " + letter,
            export_plan_ref=ref("unit-export-plan", "export-plan/1"),
            scope_ref=ref("unit-scope", "export-scope/1"),
            split_ref=ref("unit-split", "data-split/1"),
            bank_ref=ref("unit-bank", "bank-manifest/1"),
            retrieval_ref=ref(ident, "retrieval-result/1"),
            generation_input_ref=ref(ident, "generation-input/1", "public"),
            target_skill_ref=ref(ident, "compact-skill/1", "public"),
            selected_evaluation_ref=ref(ident, "evaluation/1"),
            review_ref=ref(ident, "construction-review-receipt/1"),
            qualification_ref=ref(ident, "training-target-qualification/1"),
            labels=labels,
            messages=(
                SFTMessage(
                    role="system",
                    content="Synthetic unit contract; no real training source",
                ),
                SFTMessage(role="user", content=ident),
                SFTMessage(
                    role="assistant",
                    content=json.dumps(
                        dict(
                            title="unit",
                            principle="Unit contract only",
                            when_to_apply="Synthetic test only",
                        ),
                        ensure_ascii=False,
                    ),
                ),
            ),
        )
        rows.append(row)
    items = tuple(
        DatasetItem(
            example_id=e.example_id,
            partition="train" if i == 0 else "validation",
            example_ref=example_reference(e),
        )
        for i, e in enumerate(rows)
    )
    digest = hashlib.sha256(
        json.dumps(
            [i.model_dump(mode="json") for i in items],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    m = DatasetManifest(
        kind="formal",
        export_plan_ref=rows[0].export_plan_ref,
        scope_ref=rows[0].scope_ref,
        split_ref=rows[0].split_ref,
        status="train_validation_ready",
        items=items,
        bank_refs=(rows[0].bank_ref,),
        review_refs=tuple(e.review_ref for e in rows),
        examples_sha256=digest,
    )
    mr = evidence_reference(
        m.model_dump_json().encode(), export_metadata("dataset-manifest/1")
    )
    receipt = ExportReceipt(
        export_plan_ref=m.export_plan_ref,
        kind="formal",
        dataset_ref=mr,
        example_count=2,
        status="train_validation_ready",
        decisions=tuple(
            ExportDecision(
                example_id=e.example_id,
                status="exported",
                reason_code="unit-contract-only",
                review_ref=e.review_ref,
            )
            for e in rows
        ),
    )
    return LoadedDataset(receipt, m, tuple(rows), "sft")


class UnitTrainingAuthority:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.denied = False

    def verify(
        self, plan: TrainingPlan, data: LoadedDataset, control: OperationControl
    ) -> None:
        control.checkpoint()
        assert plan.training_id.startswith("unit-sft-")
        self.calls.append("verify")
        if self.denied:
            raise PermissionError("Unit training phase denied")

    def verify_result(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        result: TrainingRunResult,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.calls.append("verify_result")


class UnitTrainingRuntime:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.error: BaseException | None = None

    def execute(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        contract: dict[str, Any],
        control: OperationControl,
    ) -> None:
        from lab_generate_skill.adapters.training.inputs import build_sft_inputs
        from lab_generate_skill.adapters.training.torch_sft import run_original_sft

        control.checkpoint()
        self.calls.append("execute")
        request = build_sft_inputs(plan, data, output)
        assert request.contract == contract
        run_original_sft(request.args, request.train, request.dev, contract, control)

    def verify(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        assert plan.model.artifact_id == "unit-no-model-weights"
        self.calls.append("verify")
        if self.error is not None:
            raise self.error

    def finish(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        contract: dict[str, Any],
        control: OperationControl,
    ) -> TrainingRunResult:
        control.checkpoint()
        self.calls.append("finish")
        assert data.receipt.dataset_ref is not None
        return TrainingRunResult(
            training_id=plan.training_id,
            dataset_ref=data.receipt.dataset_ref,
            training_release_ref=plan.training_release_ref,
            contract_sha256=hashlib.sha256(
                json.dumps(contract, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest(),
            status="completed",
            optimizer_steps=1,
            planned_optimizer_steps=1,
            checkpoint_ref=ref("unit-no-weights-checkpoint", "sft-checkpoint/1"),
            runtime_evidence_refs=(
                ref("unit-runtime-contract-only", "unit-sft-runtime/1"),
            ),
        )

    def abort(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        primary: BaseException,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.calls.append("abort")


@dataclass
class TrainingCase:
    export: ExportCase
    engineering_receipt_ref: EvidenceRef
    data: LoadedDataset
    root: Path

    def plan(self, name: str) -> TrainingPlan:
        initial = self.export.plan("training-" + name)
        sources = tuple(
            initial.sources[0].model_copy(
                update={
                    "example_id": e.example_id,
                    "legacy_id": e.legacy_id,
                    "review_ref": e.review_ref,
                    "qualification_ref": e.qualification_ref,
                }
            )
            for e in self.data.examples
        )
        read = DatasetLoadPlan(
            export_receipt_ref=evidence_reference(
                self.data.receipt.model_dump_json().encode(),
                export_metadata("export-receipt/1"),
            ),
            expected_kind="formal",
            purpose="sft",
            sources=sources,
            operation=initial.operation,
        )
        return TrainingPlan(
            training_id="unit-sft-" + name,
            dataset=read,
            training_release_ref=self.export.scope.release_ref,
            phase_authorization_ref=ref(
                "unit-phase-contract-only", "training-authorization/1"
            ),
            model=ReleaseArtifact(
                artifact_id="unit-no-model-weights",
                root=str(self.root / "unit-model"),
                files=(
                    ReleaseFile(
                        path="config.json",
                        sha256=hashlib.sha256(b"{}").hexdigest(),
                        size_bytes=2,
                        executable=False,
                    ),
                ),
            ),
            spec=TrainingSpec(max_steps=1),
        )


@pytest.fixture(scope="module")
def training_case(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TrainingCase]:
    root = tmp_path_factory.mktemp("training-consumer")
    with pytest.MonkeyPatch.context() as patch:
        c = export_case(root / "export", patch)
        receipt = export_targets(c.plan("training-fixture-export"), c.deps)
        r = evidence_reference(
            receipt.model_dump_json().encode(), export_metadata("export-receipt/1")
        )
        yield TrainingCase(c, r, contract_data(), root)
        assert c.review.control.source.native.loader.session.calls == 5
        assert len(c.review.control.wire.transport.calls) == 1
