"""Original navigation semantics through the existing read-only Evaluator port."""

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
from lab_generate_skill.domain.map_navigation_scope import NAVIGATION_PAGE_MEMBERS
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.evidence_schema import (
    MapNavigationEvidence,
    NavigationOutcome,
)

PAGE_CHECKS = ("correct_site", "page_valid", "target_path", "target_heading")
GUARD_CHECK = "original_complete_persistent_state_unchanged"
CHECKS = (*PAGE_CHECKS, GUARD_CHECK)
REQUIREMENTS = EvidenceRequirements(
    facts=tuple(
        EvidenceRequirement(name=n, content_schema=s, visibility="private")
        for n, s in (
            ("environment", "environment-selection/1"),
            ("terminal", "map-navigation-terminal-selection/1"),
            ("final_guard", "site-task-result/1"),
            ("browser_closed", "closure-receipt/1"),
        )
    )
)


class NavigationFactsLoader(Protocol):
    def __call__(
        self,
        contract: EvaluationContract,
        selected: MapNavigationEvidence,
        reader: EvidenceReader,
        control: OperationControl,
    ) -> NavigationOutcome: ...


class NavigationEvaluator:
    def __init__(
        self, selected: MapNavigationEvidence, loader: NavigationFactsLoader
    ) -> None:
        self.selected = MapNavigationEvidence.model_validate(selected)
        self.loader = loader

    @staticmethod
    def requirements(contract: EvaluationContract) -> EvidenceRequirements:
        i = contract.identity
        if (
            (i.site, i.family, i.contract_version, i.split)
            != ("map", "navigation_page_identity", 1, "train")
            or i.source_task_id not in NAVIGATION_PAGE_MEMBERS
            or contract.scope != "engineering"
            or contract.requirements != REQUIREMENTS
        ):
            raise ValueError(
                "Explicit pinned engineering navigation-page contract required"
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
        values: dict[str, bool] = {}
        status: Literal["unknown", "success", "failure"] = "unknown"
        reason = "INVALID_NAVIGATION_EVIDENCE"
        try:
            outcome = self.loader(contract, self.selected, evidence, control)
            if (
                not isinstance(outcome, NavigationOutcome)
                or (
                    outcome.state_change_requires_review is not None
                    and outcome.state_change_requires_review is not False
                )
                or (
                    outcome.selected_records_unchanged is not None
                    and outcome.selected_records_unchanged is not True
                )
            ):
                raise ValueError("Original unchanged navigation outcome required")
            if type(outcome.checks) is not tuple or any(
                type(row) is not tuple
                or len(row) != 2
                or type(row[0]) is not str
                or type(row[1]) is not bool
                for row in outcome.checks
            ):
                raise ValueError("Exact original navigation check pairs required")
            values = dict(outcome.checks)
            if len(values) != len(outcome.checks) or any(
                n not in PAGE_CHECKS or type(v) is not bool for n, v in outcome.checks
            ):
                raise ValueError("Exact original navigation page checks required")
            if (
                outcome.status not in ("success", "failure", "unknown")
                or (outcome.reward is not None and type(outcome.reward) is not float)
                or outcome.reward
                != {"success": 1.0, "failure": 0.0, "unknown": None}[outcome.status]
                or outcome.version not in (None, "site-navigation-v3")
            ):
                raise ValueError("Original navigation status/reward disagree")
            if outcome.status != "unknown" and (
                tuple(values) != PAGE_CHECKS
                or outcome.version != "site-navigation-v3"
                or all(values.values()) != (outcome.status == "success")
            ):
                raise ValueError("Complete original navigation checks required")
            values[GUARD_CHECK] = True
            status = outcome.status
            reason = (
                "INCOMPLETE_NAVIGATION_FACTS"
                if status == "unknown"
                else (
                    "ORIGINAL_NAVIGATION_MATCH"
                    if status == "success"
                    else "ORIGINAL_NAVIGATION_MISMATCH"
                )
            )
        except (EvidenceError, OwnershipConflict) as error:
            values, reason = {}, error.reason_code
        except IncompleteAnswerEvidence:
            values, reason = {}, "INCOMPLETE_ACTOR_EXECUTION"
        except ValueError:
            values, reason = {}, "INVALID_NAVIGATION_EVIDENCE"
        control.checkpoint()
        refs = self.selected.evidence_refs()
        return Evaluation(
            identity=contract.identity,
            attempt_id=contract.attempt_id,
            contract_ref=contract.task_contract_ref,
            evaluator_id="map-navigation-page",
            evaluator_version="site-navigation-v3-current-v1",
            status=status,
            reward=None if status == "unknown" else int(status == "success"),
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
                for n in CHECKS
            ),
            reason_code=reason,
            evidence=refs,
        )
