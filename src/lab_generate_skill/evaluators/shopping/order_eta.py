"""Original selected query checks plus complete-native integrity; no live effects."""

from pydantic import ValidationError
from lab_generate_skill.domain.evaluation import (
    EvaluationContract,
    Evaluation,
    CheckResult,
)
from lab_generate_skill.domain.evidence import (
    EvidenceRequirement,
    EvidenceRequirements,
    EvidenceRef,
)
from lab_generate_skill.domain.errors import EvidenceError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping.evidence_schema import OrderEtaEvidence
from lab_generate_skill.task_families.recorded_order_eta import (
    decide_eta,
    EtaOutcome,
    CHECKS,
)
from lab_generate_skill.evaluators.evidence import EvaluationEvidence
from lab_generate_skill.domain.errors import IncompleteAnswerEvidence
from .order_eta_inputs import load_eta_facts

REQUIREMENTS = EvidenceRequirements(
    facts=tuple(
        EvidenceRequirement(name=name, content_schema=schema, visibility="private")
        for name, schema in (
            ("order_before", "site-task-result/1"),
            ("order_after", "site-task-result/1"),
            ("final_page", "browser-capture-result/1"),
            ("sealed_trace", "interaction-trace/1"),
        )
    )
)


class OrderEtaEvaluator:
    def __init__(self, selection: OrderEtaEvidence) -> None:
        self.selection = OrderEtaEvidence.model_validate(selection)

    def requirements(self, contract: EvaluationContract) -> EvidenceRequirements:
        if (
            contract.identity.site,
            contract.identity.family,
            contract.identity.contract_version,
        ) != (
            "shopping",
            "recorded_order_eta",
            1,
        ) or contract.requirements != REQUIREMENTS:
            raise ValueError(
                "Unsupported Shopping task or frozen evidence requirements"
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
        refs: tuple[EvidenceRef, ...] = tuple(
            ref
            for pair in (
                self.selection.before,
                self.selection.after,
                self.selection.page,
            )
            if pair is not None
            for ref in (pair.intent_ref, pair.result_ref)
        )
        if self.selection.trace_ref is not None:
            refs += (self.selection.trace_ref,)
        try:
            facts = load_eta_facts(
                contract, self.selection, EvaluationEvidence(evidence, control)
            )
            outcome = decide_eta(
                before=facts.before.legacy_reference(),
                after=facts.after.legacy_reference(),
                before_core=facts.before.protected.core_fingerprint,
                after_core=facts.after.protected.core_fingerprint,
                page_url=facts.page.url,
                http_status=facts.page.http_status,
                login_page=facts.page.login_page,
                error_page=facts.page.error_page,
                site_origin=facts.public.start_url,
                answer=facts.answer,
            )
        except EvidenceError as error:
            outcome = EtaOutcome("unknown", None, (None,) * 5, error.reason_code)
        except IncompleteAnswerEvidence:
            outcome = EtaOutcome(
                "unknown", None, (None,) * 5, "INCOMPLETE_ACTOR_EXECUTION"
            )
        except (ValidationError, ValueError):
            outcome = EtaOutcome(
                "unknown", None, (None,) * 5, "INVALID_CAPTURE_EVIDENCE"
            )
        control.checkpoint()
        checks = tuple(
            CheckResult(
                name=name,
                status="unknown" if value is None else "pass" if value else "fail",
                reason_code=(
                    outcome.reason
                    if value is None
                    else "MATCH" if value else "MISMATCH"
                ),
                evidence=refs,
            )
            for name, value in zip(CHECKS, outcome.checks, strict=True)
        )
        return Evaluation(
            identity=contract.identity,
            attempt_id=contract.attempt_id,
            contract_ref=contract.task_contract_ref,
            evaluator_id="shopping-recorded-order-eta",
            evaluator_version="shopping-complete-local-training-query-v1",
            status=outcome.status,
            reward=outcome.reward,
            checks=checks,
            reason_code=outcome.reason,
            evidence=refs,
        )
