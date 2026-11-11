"""Qualified original target -> immutable examples/manifest/receipt, no training."""

from dataclasses import dataclass
import hashlib
import json
from lab_generate_skill.domain.export import (
    ExportPlan,
    ExportScope,
    ExportReceipt,
    ExportDecision,
)
from lab_generate_skill.domain.dataset import (
    DatasetManifest,
    DatasetItem,
    TrainingExample,
)
from lab_generate_skill.domain.data_scope import SplitManifest
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.export import ExportInputs, ExportAuthority
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.policies.dataset_split import partition_examples
from .teacher_actor_reads import canonical
from .context_evidence import publish_raw
from .export_examples import prepare_export_examples, ExportPreparationUnconfirmed
from lab_generate_skill.policies.dataset_manifest import (
    export_metadata,
    example_reference,
    make_manifest,
)


@dataclass(frozen=True)
class ExportDeps:
    evidence: EvidenceStore
    inputs: ExportInputs
    authority: ExportAuthority
    controls: OperationControls

    def __post_init__(self) -> None:
        if any(
            not callable(getattr(p, name, None))
            for p, name in (
                (self.evidence, "read"),
                (self.evidence, "put"),
                (self.inputs, "load"),
                (self.authority, "verify_scope"),
                (self.authority, "admit"),
                (self.controls, "bind"),
            )
        ):
            raise ValueError(
                "Explicit original export proof/store/authority/control required"
            )


class ExportUnconfirmed(RuntimeError):
    def __init__(
        self,
        plan: ExportPlan,
        phase: str,
        primary: BaseException,
        retained: tuple[EvidenceRef, ...],
        decisions: tuple[ExportDecision, ...],
    ) -> None:
        self.plan, self.phase, self.primary, self.retained, self.decisions = (
            plan,
            phase,
            primary,
            retained,
            decisions,
        )
        super().__init__(
            "Export unconfirmed; retain exact refs, never dispatch or recreate original tasks"
        )


def export_targets(plan: ExportPlan, deps: ExportDeps) -> ExportReceipt:
    plan = ExportPlan.model_validate(plan)
    retained: list[EvidenceRef] = []
    decisions: tuple[ExportDecision, ...] = ()
    phase = "original_scope_and_sources"
    try:
        control = deps.controls.bind(plan.operation)
        control.checkpoint()
        scope = canonical(
            plan.scope_ref,
            "export-scope/1",
            ExportScope,
            deps.evidence,
            control,
            1024**2,
        )
        split = canonical(
            plan.split_ref,
            "data-split/1",
            SplitManifest,
            deps.evidence,
            control,
            16 * 1024**2,
        )
        raw = plan.model_dump_json().encode()
        plan_ref = evidence_reference(raw, export_metadata("export-plan/1"))
        examples, decisions = prepare_export_examples(
            plan, plan_ref, scope, split, deps.inputs, deps.authority, control
        )
        manifest = make_manifest(plan, plan_ref, examples) if examples else None
        dataset_ref = (
            evidence_reference(
                manifest.model_dump_json().encode(),
                export_metadata("dataset-manifest/1"),
            )
            if manifest is not None
            else None
        )
        receipt = ExportReceipt(
            export_plan_ref=plan_ref,
            kind=plan.kind,
            dataset_ref=dataset_ref,
            example_count=len(examples),
            status=manifest.status if manifest is not None else "empty",
            decisions=decisions,
        )
        # All original evidence/eligibility and byte/schema checks before first put.
        phase = "publish_original_plan"
        publish_raw(
            deps.evidence, raw, export_metadata("export-plan/1"), retained, control
        )
        for example in examples:
            phase = "publish_example"
            publish_raw(
                deps.evidence,
                example.model_dump_json().encode(),
                export_metadata("training-example/1"),
                retained,
                control,
            )
        if manifest is not None:
            phase = "publish_manifest"
            publish_raw(
                deps.evidence,
                manifest.model_dump_json().encode(),
                export_metadata("dataset-manifest/1"),
                retained,
                control,
            )
        phase = "publish_receipt"
        publish_raw(
            deps.evidence,
            receipt.model_dump_json().encode(),
            export_metadata("export-receipt/1"),
            retained,
            control,
        )
        return receipt
    except BaseException as error:
        if isinstance(error, ExportPreparationUnconfirmed):
            decisions = error.decisions
            primary = error.primary
        else:
            primary = error
        raise ExportUnconfirmed(
            plan, phase, primary, tuple(retained), decisions
        ) from error
