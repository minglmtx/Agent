"""Original four navigation checks through the existing read-only Evaluator port."""

from urllib.parse import urlsplit
from lab_generate_skill.domain.evaluation import (
    Evaluation,
    EvaluationContract,
    CheckResult,
)
from lab_generate_skill.domain.evidence import EvidenceRequirement, EvidenceRequirements
from lab_generate_skill.domain.errors import EvidenceError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping_admin.evidence_schema import (
    AdminNavigationEvidence,
)
from lab_generate_skill.evaluators.evidence import EvaluationEvidence
from .navigation_evaluation_inputs import (
    load_navigation_facts,
    IncompleteNavigationExecution,
)
from .navigation_predicates import navigation_checks

CHECKS = (
    "same_local_deployment",
    "valid_authenticated_page",
    "target_page_url",
    "target_page_heading",
)
REQUIREMENTS = EvidenceRequirements(
    facts=tuple(
        EvidenceRequirement(name=name, content_schema=schema, visibility="private")
        for name, schema in (
            ("browser", "browser-resource-spec/4"),
            ("final_page", "browser-capture-result/1"),
            ("sealed_trace", "interaction-trace/1"),
        )
    )
)


class AdminNavigationEvaluator:
    def __init__(self, selected: AdminNavigationEvidence) -> None:
        self.selected = AdminNavigationEvidence.model_validate(selected)

    @staticmethod
    def requirements(contract: EvaluationContract) -> EvidenceRequirements:
        if (
            contract.identity.site,
            contract.identity.family,
            contract.identity.contract_version,
            contract.identity.split,
        ) != (
            "shopping_admin",
            "page_navigation",
            1,
            "train",
        ) or contract.requirements != REQUIREMENTS:
            raise ValueError(
                "Explicit selected navigation evaluation contract required"
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
        unknown: str | None = None
        values: tuple[bool, ...] = ()
        try:
            facts = load_navigation_facts(
                contract, self.selected, EvaluationEvidence(evidence, control)
            )
            checks = navigation_checks(
                facts.spec, facts.page, urlsplit(facts.public.start_url).netloc
            )
            if tuple(checks) != CHECKS:
                raise ValueError("Original four navigation checks required")
            values = tuple(checks.values())
        except EvidenceError as error:
            unknown = error.reason_code
        except IncompleteNavigationExecution:
            unknown = "INCOMPLETE_NAVIGATION_EXECUTION"
        except ValueError:
            unknown = "INVALID_NAVIGATION_EVIDENCE"
        control.checkpoint()
        success = all(values)
        refs = self.selected.evidence_refs()
        return Evaluation(
            identity=contract.identity,
            attempt_id=contract.attempt_id,
            contract_ref=contract.task_contract_ref,
            evaluator_id="admin-page-navigation",
            evaluator_version="admin-page-navigation-v1-current1",
            status="unknown" if unknown else "success" if success else "failure",
            reward=None if unknown else int(success),
            checks=tuple(
                CheckResult(
                    name=name,
                    status=(
                        "unknown" if unknown else "pass" if values[index] else "fail"
                    ),
                    reason_code=unknown or ("MATCH" if values[index] else "MISMATCH"),
                    evidence=refs,
                )
                for index, name in enumerate(CHECKS)
            ),
            reason_code=unknown
            or ("ALL_CHECKS_PASS" if success else "REQUIRED_CHECK_FAILED"),
            evidence=refs,
        )
