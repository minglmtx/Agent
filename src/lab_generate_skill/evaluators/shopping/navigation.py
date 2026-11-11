"""Original v3 category page rules after mandatory complete provenance/guard."""

from typing import Protocol, Literal
from lab_generate_skill.domain.evaluation import (
    EvaluationContract,
    Evaluation,
    CheckResult,
)
from lab_generate_skill.domain.evidence import EvidenceRequirement, EvidenceRequirements
from lab_generate_skill.domain.errors import (
    EvidenceError,
    OwnershipConflict,
    IncompleteAnswerEvidence,
)
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping.navigation_evidence import (
    CategoryNavigationEvidence,
)
from lab_generate_skill.sites.shopping.navigation_evaluation_reads import (
    CategoryNavigationFacts,
)
from lab_generate_skill.sites.shopping.tasks.navigation_checks import (
    category_navigation_checks,
    CHECKS,
)

GUARD = "original_complete_persistent_state_unchanged"
REQUIREMENTS = EvidenceRequirements(
    facts=tuple(
        EvidenceRequirement(name=n, content_schema=s, visibility="private")
        for n, s in (
            ("environment", "environment-selection/1"),
            ("initial_checks", "initial-state-checks/1"),
            ("sealed_trace", "interaction-trace/1"),
            ("sealed_journal", "trace-journal-snapshot/1"),
            ("final_page", "browser-capture-result/1"),
            ("final_guard", "site-task-result/1"),
            ("browser_closed", "closure-receipt/1"),
        )
    )
)


class CategoryFactsLoader(Protocol):
    def __call__(
        self,
        contract: EvaluationContract,
        selected: CategoryNavigationEvidence,
        reader: EvidenceReader,
        control: OperationControl,
    ) -> CategoryNavigationFacts: ...


class CategoryNavigationEvaluator:
    def __init__(
        self, selected: CategoryNavigationEvidence, loader: CategoryFactsLoader
    ) -> None:
        self.selected = CategoryNavigationEvidence.model_validate(selected)
        if loader is None:
            raise ValueError("Original category provenance loader required")
        self.loader = loader

    @staticmethod
    def requirements(contract: EvaluationContract) -> EvidenceRequirements:
        i = contract.identity
        if (
            (i.site, i.family, i.contract_version, i.split)
            != ("shopping", "page_navigation", 1, "train")
            or contract.scope != "engineering"
            or contract.requirements != REQUIREMENTS
        ):
            raise ValueError("Explicit original engineering category contract required")
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
        values: dict[str, bool] = {}
        status: Literal["success", "failure", "unknown"] = "unknown"
        reason = "INVALID_CATEGORY_EVIDENCE"
        try:
            facts = self.loader(contract, self.selected, evidence, control)
            values = category_navigation_checks(
                facts.private, facts.page, facts.site_origin
            )
            if tuple(values) != CHECKS:
                raise ValueError("Complete original category page rules required")
            values[GUARD] = True
            status = "success" if all(values.values()) else "failure"
            reason = (
                "ORIGINAL_CATEGORY_MATCH"
                if status == "success"
                else "ORIGINAL_CATEGORY_MISMATCH"
            )
        except (EvidenceError, OwnershipConflict) as error:
            values, reason = {}, error.reason_code
        except IncompleteAnswerEvidence:
            values, reason = {}, "INCOMPLETE_ACTOR_EXECUTION"
        except ValueError:
            values, reason = {}, "INVALID_CATEGORY_EVIDENCE"
        control.checkpoint()
        refs = self.selected.evidence_refs()
        return Evaluation(
            identity=contract.identity,
            attempt_id=contract.attempt_id,
            contract_ref=contract.task_contract_ref,
            evaluator_id="shopping-category-navigation",
            evaluator_version="site-navigation-v3-current-v1",
            status=status,
            reward=None if status == "unknown" else int(status == "success"),
            reason_code=reason,
            checks=tuple(
                CheckResult(
                    name=n,
                    status=(
                        "unknown"
                        if n not in values
                        else "pass" if values[n] else "fail"
                    ),
                    reason_code=(
                        reason
                        if n not in values
                        else "MATCH" if values[n] else "MISMATCH"
                    ),
                    evidence=refs,
                )
                for n in (*CHECKS, GUARD)
            ),
            evidence=refs,
        )
