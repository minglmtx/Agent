"""Original Group goal and project guard on complete readonly selected evidence."""

from typing import Protocol
from pydantic import ValidationError
from lab_generate_skill.domain.evaluation import (
    Evaluation,
    EvaluationContract,
    CheckResult,
)
from lab_generate_skill.domain.evidence import (
    EvidenceRequirement,
    EvidenceRequirements,
    EvidenceRef,
)
from lab_generate_skill.domain.errors import (
    EvidenceError,
    OwnershipConflict,
    IncompleteAnswerEvidence,
)
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.gitlab.evidence_schema import (
    GroupEvidence,
    GroupFacts,
    GroupOutcome,
    GroupSpec,
    GroupNativeState,
)
from lab_generate_skill.sites.gitlab.evidence_schema import GitlabPageHealth
from lab_generate_skill.evaluators.evidence import EvaluationEvidence
from lab_generate_skill.evaluators.browser_answer import trace_answer

REQUIREMENTS = EvidenceRequirements(
    facts=tuple(
        EvidenceRequirement(name=name, content_schema=schema, visibility="private")
        for name, schema in (
            ("environment", "environment-selection/1"),
            ("browser", "browser-resource-spec/4"),
            ("native_before", "site-task-result/1"),
            ("native_after", "site-task-result/1"),
            ("final_page", "browser-capture-result/1"),
            ("sealed_trace", "interaction-trace/1"),
        )
    )
)


class GroupFactsLoader(Protocol):
    def __call__(
        self,
        contract: EvaluationContract,
        selected: GroupEvidence,
        reader: EvidenceReader,
        control: OperationControl,
    ) -> GroupFacts: ...


class GroupRule(Protocol):
    def __call__(
        self,
        spec: GroupSpec,
        before: GroupNativeState | None,
        after: GroupNativeState | None,
        page: GitlabPageHealth | None,
        *,
        site_origin: str,
        selected_projects_unchanged: bool | None,
        runtime_error: bool = False,
    ) -> GroupOutcome: ...


class GroupEvaluator:
    def __init__(
        self, selected: GroupEvidence, loader: GroupFactsLoader, decide: GroupRule
    ) -> None:
        self.selected = GroupEvidence.model_validate(selected)
        self.loader, self.decide = loader, decide

    @staticmethod
    def requirements(contract: EvaluationContract) -> EvidenceRequirements:
        if (
            contract.identity.site,
            contract.identity.family,
            contract.identity.contract_version,
            contract.identity.split,
            contract.scope,
        ) != (
            "gitlab",
            "group_creation",
            1,
            "train",
            "engineering",
        ) or contract.requirements != REQUIREMENTS:
            raise ValueError(
                "Unsupported selected engineering Group evaluation contract"
            )
        return REQUIREMENTS

    def evaluate(
        self,
        contract: EvaluationContract,
        evidence: EvidenceReader,
        control: OperationControl,
    ) -> Evaluation:
        contract = EvaluationContract.model_validate(contract)
        self.requirements(contract)
        control.checkpoint()
        refs: tuple[EvidenceRef, ...] = tuple(
            ref
            for ref in (self.selected.environment_ref, self.selected.browser_spec_ref)
            if ref is not None
        )
        refs += tuple(
            ref
            for pair in (self.selected.before, self.selected.after, self.selected.page)
            if pair is not None
            for ref in (pair.intent_ref, pair.result_ref)
        )
        if self.selected.trace_ref is not None:
            refs += (self.selected.trace_ref,)
        values: tuple[tuple[str, bool | None], ...]
        try:
            facts = self.loader(contract, self.selected, evidence, control)
            if facts.trace.stop_reason in ("error", "uncertain", "cancelled"):
                raise IncompleteAnswerEvidence(
                    "Original Group Actor execution incomplete"
                )
            trace_answer(
                facts.trace, facts.public, EvaluationEvidence(evidence, control)
            )
            projects = facts.before.project_copy == facts.after.project_copy
            outcome = self.decide(
                facts.spec,
                facts.before.state,
                facts.after.state,
                facts.page,
                site_origin=facts.site_origin,
                selected_projects_unchanged=projects,
            )
            status, reward = outcome.status, outcome.reward
            reason = outcome.reason or (
                "GOAL_MATCH" if status == "success" else "GOAL_MISMATCH"
            )
            # Preserve the external original guard as explicit evidence. It
            # does not replace goal checks or turn goal+guard success into failure.
            values = outcome.checks + (("selected_projects_preserved", projects),)
            if not outcome.checks and status == "unknown":
                values = (("complete_original_evidence", None),) + values
            if outcome.state_change_requires_review != (not projects):
                raise ValueError("Original Group protected-project review flag differs")
        except (EvidenceError, OwnershipConflict) as error:
            status, reward, reason = "unknown", None, error.reason_code
            values = (("complete_original_evidence", None),)
        except IncompleteAnswerEvidence:
            status, reward, reason = "unknown", None, "INCOMPLETE_ACTOR_EXECUTION"
            values = (("complete_original_evidence", None),)
        except (ValidationError, ValueError):
            status, reward, reason = "unknown", None, "INVALID_CAPTURE_EVIDENCE"
            values = (("complete_original_evidence", None),)
        control.checkpoint()
        checks = tuple(
            CheckResult(
                name=name,
                status="unknown" if value is None else "pass" if value else "fail",
                reason_code=(
                    reason if value is None else "MATCH" if value else "MISMATCH"
                ),
                evidence=refs,
            )
            for name, value in values
        )
        return Evaluation(
            identity=contract.identity,
            attempt_id=contract.attempt_id,
            contract_ref=contract.task_contract_ref,
            evaluator_id="gitlab-group-creation",
            evaluator_version="gitlab-complete-native-group-v1",
            status=status,
            reward=reward,
            checks=checks,
            reason_code=reason,
            evidence=refs,
        )
