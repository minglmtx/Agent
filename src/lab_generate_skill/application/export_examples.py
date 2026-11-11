"""One shared original-source reconstruction for exporter and dataset consumer."""

import json
from lab_generate_skill.domain.export import (
    ExportPlan,
    ExportScope,
    ExportDecision,
    ExportAdmission,
)
from lab_generate_skill.domain.dataset import TrainingExample, SFTMessage
from lab_generate_skill.domain.data_scope import SplitManifest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.export import ExportInputs, ExportAuthority
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.export_eligibility import rejection


class ExportPreparationUnconfirmed(RuntimeError):
    def __init__(
        self,
        primary: BaseException,
        examples: tuple[TrainingExample, ...],
        decisions: tuple[ExportDecision, ...],
    ) -> None:
        self.primary, self.examples, self.decisions = primary, examples, decisions
        super().__init__(
            "Export source preparation unconfirmed; retain completed metadata, no publication"
        )


def prepare_export_examples(
    plan: ExportPlan,
    plan_ref: EvidenceRef,
    scope: ExportScope,
    split: SplitManifest,
    inputs: ExportInputs,
    authority: ExportAuthority,
    control: OperationControl,
) -> tuple[tuple[TrainingExample, ...], tuple[ExportDecision, ...]]:
    examples: list[TrainingExample] = []
    decisions: list[ExportDecision] = []
    try:
        return _prepare_export_examples(
            plan,
            plan_ref,
            scope,
            split,
            inputs,
            authority,
            control,
            examples,
            decisions,
        )
    except BaseException as error:
        raise ExportPreparationUnconfirmed(
            error, tuple(examples), tuple(decisions)
        ) from error


def _prepare_export_examples(
    plan: ExportPlan,
    plan_ref: EvidenceRef,
    scope: ExportScope,
    split: SplitManifest,
    inputs: ExportInputs,
    authority: ExportAuthority,
    control: OperationControl,
    examples: list[TrainingExample],
    decisions: list[ExportDecision],
) -> tuple[tuple[TrainingExample, ...], tuple[ExportDecision, ...]]:
    if (scope.kind, scope.split_ref, scope.release_ref) != (
        plan.kind,
        plan.split_ref,
        plan.release_ref,
    ):
        raise EvidenceIntegrityError("Export changed actual frozen scope/split/release")
    for task in scope.allowed_tasks:
        split.member(task)
    authority.verify_scope(plan, scope, split, control)
    seen_aliases: set[str] = set()
    for source in plan.sources:
        control.checkpoint()
        material = inputs.load(source, plan, scope, split, control)
        identity = material.progress.plan.task.identity
        if (
            source.example_id != identity.task_id
            or source.legacy_id != identity.task_id
            or identity.split != "train"
            or material.member != split.member(identity)
        ):
            raise EvidenceIntegrityError(
                "Source/example identity differs from exact frozen train member"
            )
        if seen_aliases.intersection(material.member.source_ids):
            raise EvidenceIntegrityError("Export repeats an original task/source alias")
        seen_aliases.update(material.member.source_ids)
        admission = ExportAdmission.model_validate(
            authority.admit(plan, scope, source, material, control)
        )
        reason = rejection(plan, scope, material, admission)
        if reason is not None:
            status = (
                "no_positive_target"
                if reason == "no_positive_target"
                else (
                    "review_unconfirmed"
                    if reason == "review_not_verified"
                    else "ineligible"
                )
            )
            decisions.append(
                ExportDecision.model_validate(
                    dict(
                        example_id=source.example_id,
                        status=status,
                        reason_code=reason,
                        review_ref=source.review_ref,
                    )
                )
            )
            continue
        target, evaluated = (
            material.selected_skill,
            material.current.plan.selected_evaluation_ref,
        )
        if (
            target is None
            or evaluated is None
            or material.current.selected_skill_ref is None
        ):
            raise EvidenceIntegrityError(
                "Eligible target has no exact selected native evidence"
            )
        messages = tuple(
            SFTMessage(role=m.role, content=m.content) for m in material.prompt.messages
        )
        example = TrainingExample(
            template=material.prompt.prompt_version,
            kind=plan.kind,
            example_id=source.example_id,
            legacy_id=source.legacy_id,
            task=identity,
            goal_group_id=material.member.goal_group_id,
            group_goal=material.member.public_goal,
            export_plan_ref=plan_ref,
            scope_ref=plan.scope_ref,
            split_ref=plan.split_ref,
            bank_ref=material.progress.plan.retrieval_scope.bank_ref,
            retrieval_ref=material.progress.plan.retrieval_ref,
            generation_input_ref=material.generation_input_ref,
            target_skill_ref=material.current.selected_skill_ref,
            selected_evaluation_ref=evaluated,
            review_ref=source.review_ref,
            qualification_ref=source.qualification_ref,
            labels=material.qualification.labels,
            messages=(
                messages[0],
                messages[1],
                SFTMessage(
                    role="assistant",
                    content=json.dumps(target.model_payload(), ensure_ascii=False),
                ),
            ),
        )
        examples.append(example)
        decisions.append(
            ExportDecision(
                example_id=source.example_id,
                status="exported",
                reason_code="qualified_selected_target",
                review_ref=source.review_ref,
            )
        )
    authority.verify_scope(plan, scope, split, control)
    control.checkpoint()
    return tuple(examples), tuple(decisions)
