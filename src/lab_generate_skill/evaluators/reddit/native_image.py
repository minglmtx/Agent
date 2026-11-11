"""Original conditional image goals over complete sealed facts; no live effects."""

from typing import Protocol
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
from lab_generate_skill.domain.errors import EvidenceError, OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.reddit.evidence_schema import (
    ImageEvidence,
    ImageFacts,
    ImageOutcome,
    RedditPageHealth,
    CHECKS,
    NativeImageSpec,
    ImageReference,
    NativeCapture,
)
from lab_generate_skill.evaluators.evidence import EvaluationEvidence
from lab_generate_skill.domain.errors import IncompleteAnswerEvidence
from lab_generate_skill.evaluators.browser_answer import (
    trace_answer,
)

REQUIREMENTS = EvidenceRequirements(
    facts=tuple(
        EvidenceRequirement(name=name, content_schema=schema, visibility="private")
        for name, schema in (
            ("environment", "environment-selection/1"),
            ("browser", "browser-resource-spec/3"),
            ("native_before", "site-task-result/1"),
            ("native_after", "site-task-result/1"),
            ("final_page", "browser-capture-result/1"),
            ("sealed_trace", "interaction-trace/1"),
            ("original_trace_journal", "trace-journal-snapshot/1"),
        )
    )
)


class ImageFactsLoader(Protocol):
    def __call__(
        self,
        contract: EvaluationContract,
        selected: ImageEvidence,
        reader: EvidenceReader,
        control: OperationControl,
    ) -> ImageFacts: ...


class ImageRule(Protocol):
    def __call__(
        self,
        spec: NativeImageSpec,
        reference: ImageReference | None,
        after: NativeCapture | None,
        page: RedditPageHealth | None,
        last_issued_ax: str | None,
        *,
        site_origin: str,
        runtime_error: bool = False,
    ) -> ImageOutcome: ...


class ImageEvaluator:
    def __init__(
        self, selected: ImageEvidence, loader: ImageFactsLoader, decide: ImageRule
    ) -> None:
        self.selected = ImageEvidence.model_validate(selected)
        self.loader, self.decide = loader, decide

    def requirements(self, contract: EvaluationContract) -> EvidenceRequirements:
        if (
            contract.identity.site,
            contract.identity.family,
            contract.identity.contract_version,
            contract.identity.split,
            contract.scope,
        ) != (
            "reddit",
            "native_image_submission",
            1,
            "train",
            "engineering",
        ) or contract.requirements != REQUIREMENTS:
            raise ValueError(
                "Unsupported selected engineering Reddit evaluation contract"
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
        for ref in (self.selected.trace_ref, self.selected.trace_snapshot_ref):
            if ref is not None:
                refs += (ref,)
        try:
            facts = self.loader(contract, self.selected, evidence, control)
            if facts.trace.stop_reason in ("error", "uncertain", "cancelled"):
                raise IncompleteAnswerEvidence(
                    "Original Reddit Actor execution incomplete"
                )
            # Native image completion has no answer-text correctness condition.
            # Still verify every actual browser return without requiring a chat.
            trace_answer(
                facts.trace, facts.public, EvaluationEvidence(evidence, control)
            )
            outcome = self.decide(
                facts.spec,
                facts.reference,
                facts.after,
                facts.page,
                facts.last_issued_ax,
                site_origin=facts.public.start_url,
            )
        except (EvidenceError, OwnershipConflict) as error:
            outcome = ImageOutcome(
                "unknown",
                None,
                tuple((name, None) for name in CHECKS),
                error.reason_code,
            )
        except IncompleteAnswerEvidence:
            outcome = ImageOutcome(
                "unknown",
                None,
                tuple((name, None) for name in CHECKS),
                "INCOMPLETE_ACTOR_EXECUTION",
            )
        except (ValidationError, ValueError):
            outcome = ImageOutcome(
                "unknown",
                None,
                tuple((name, None) for name in CHECKS),
                "INVALID_CAPTURE_EVIDENCE",
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
            for name, value in outcome.checks
        )
        return Evaluation(
            identity=contract.identity,
            attempt_id=contract.attempt_id,
            contract_ref=contract.task_contract_ref,
            evaluator_id="reddit-native-image",
            evaluator_version="reddit-native-image-v1",
            status=outcome.status,
            reward=outcome.reward,
            checks=checks,
            reason_code=outcome.reason,
            evidence=refs,
        )
