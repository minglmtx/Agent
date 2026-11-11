"""Original four Admin update checks, reading only explicitly selected evidence.

This task judgment is not source admission or independent release/closure review.
Absent evidence, target or valid execution remains unknown, never zero reward.
"""

import json
from urllib.parse import urlsplit
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
from lab_generate_skill.domain.errors import EvidenceError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.task_families.html_text import plain_text
from lab_generate_skill.sites.shopping_admin.evidence_schema import (
    ProductDescriptionEvidence,
)
from lab_generate_skill.evaluators.evidence import EvaluationEvidence
from .product_description_inputs import load_description_facts, IncompleteExecution

CHECKS = (
    "same_local_deployment",
    "valid_authenticated_page",
    "persisted_requested_value",
    "other_records_unchanged",
)
REQUIREMENTS = EvidenceRequirements(
    facts=tuple(
        EvidenceRequirement(name=name, content_schema=schema, visibility="private")
        for name, schema in (
            ("product_before", "site-task-result/1"),
            ("product_after", "site-task-result/1"),
            ("final_page", "browser-capture-result/1"),
            ("sealed_trace", "interaction-trace/1"),
        )
    )
)


class ProductDescriptionEvaluator:
    def __init__(self, selection: ProductDescriptionEvidence) -> None:
        self.selection = ProductDescriptionEvidence.model_validate(selection)

    def requirements(self, contract: EvaluationContract) -> EvidenceRequirements:
        if (
            contract.identity.site,
            contract.identity.family,
            contract.identity.contract_version,
        ) != ("shopping_admin", "product_description", 1):
            raise ValueError("Unsupported selected Admin task family")
        if contract.requirements != REQUIREMENTS:
            raise ValueError(
                "Frozen evaluation requirements differ from selected capture contract"
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
        unknown: str | None = None
        values: tuple[bool, ...] = ()
        try:
            facts = load_description_facts(
                contract, self.selection, EvaluationEvidence(evidence, control)
            )
            assert facts.after.target_record_json is not None
            row = json.loads(facts.after.target_record_json)
            values = (
                urlsplit(facts.page.url).netloc
                == urlsplit(facts.public.start_url).netloc,
                not (facts.page.login or facts.page.page_error),
                plain_text(row.get("description"))
                == plain_text(facts.spec.description),
                (facts.before.other_product_count, facts.before.other_products_sha256)
                == (facts.after.other_product_count, facts.after.other_products_sha256),
            )
        except EvidenceError as error:
            unknown = error.reason_code
        except IncompleteExecution:
            unknown = "INCOMPLETE_EXECUTION_OR_TARGET"
        except (ValidationError, ValueError):
            unknown = "INVALID_CAPTURE_EVIDENCE"
        control.checkpoint()
        checks = tuple(
            CheckResult(
                name=name,
                status=("unknown" if unknown else "pass" if values[index] else "fail"),
                reason_code=unknown or ("MATCH" if values[index] else "MISMATCH"),
                evidence=refs,
            )
            for index, name in enumerate(CHECKS)
        )
        success = all(values)
        return Evaluation(
            identity=contract.identity,
            attempt_id=contract.attempt_id,
            contract_ref=contract.task_contract_ref,
            evaluator_id="admin-product-description",
            evaluator_version="legacy-admin-update-v1",
            status="unknown" if unknown else "success" if success else "failure",
            reward=None if unknown else int(success),
            checks=checks,
            reason_code=unknown
            or ("ALL_CHECKS_PASS" if success else "REQUIRED_CHECK_FAILED"),
            evidence=refs,
        )
