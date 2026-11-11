"""Original seven conditions over sealed selected evidence; no live site effects."""

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
from lab_generate_skill.sites.gitlab.evidence_schema import (
    SshKeyEvidence,
    SshKeyFacts,
    SshKeyOutcome,
    SshKeySpec,
    SshKeyNativeState,
    GitlabPageHealth,
    CHECKS,
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
            ("browser", "browser-resource-spec/4"),
            ("native_before", "site-task-result/1"),
            ("native_after", "site-task-result/1"),
            ("final_page", "browser-capture-result/1"),
            ("sealed_trace", "interaction-trace/1"),
        )
    )
)


class SshFactsLoader(Protocol):
    def __call__(
        self,
        contract: EvaluationContract,
        selected: SshKeyEvidence,
        reader: EvidenceReader,
        control: OperationControl,
    ) -> SshKeyFacts: ...


class SshRule(Protocol):
    def __call__(
        self,
        spec: SshKeySpec,
        before: SshKeyNativeState | None,
        after: SshKeyNativeState | None,
        page: GitlabPageHealth | None,
        *,
        site_origin: str,
        runtime_error: bool = False,
    ) -> SshKeyOutcome: ...


class SshKeyEvaluator:
    def __init__(
        self, selected: SshKeyEvidence, loader: SshFactsLoader, decide: SshRule
    ) -> None:
        self.selected = SshKeyEvidence.model_validate(selected)
        self.loader, self.decide = loader, decide

    def requirements(self, contract: EvaluationContract) -> EvidenceRequirements:
        if (
            contract.identity.site,
            contract.identity.family,
            contract.identity.contract_version,
            contract.identity.split,
            contract.scope,
        ) != (
            "gitlab",
            "profile_ssh_key",
            1,
            "train",
            "engineering",
        ) or contract.requirements != REQUIREMENTS:
            raise ValueError("Unsupported selected engineering SSH evaluation contract")
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
        try:
            facts = self.loader(contract, self.selected, evidence, control)
            if facts.trace.stop_reason in ("error", "uncertain", "cancelled"):
                raise IncompleteAnswerEvidence(
                    "Original SSH Actor execution incomplete"
                )
            # The original supplied-key meaning has no answer-text correctness
            # condition. Verify actual browser returns without requiring a chat.
            trace_answer(
                facts.trace, facts.public, EvaluationEvidence(evidence, control)
            )
            outcome = self.decide(
                facts.spec,
                facts.before,
                facts.after,
                facts.page,
                site_origin=facts.public.start_url,
            )
        except (EvidenceError, OwnershipConflict) as error:
            outcome = SshKeyOutcome(
                "unknown", None, (None,) * len(CHECKS), error.reason_code
            )
        except IncompleteAnswerEvidence:
            outcome = SshKeyOutcome(
                "unknown", None, (None,) * len(CHECKS), "INCOMPLETE_ACTOR_EXECUTION"
            )
        except (ValidationError, ValueError):
            outcome = SshKeyOutcome(
                "unknown", None, (None,) * len(CHECKS), "INVALID_CAPTURE_EVIDENCE"
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
            evaluator_id="gitlab-profile-ssh-key",
            evaluator_version="gitlab-complete-native-ssh-v2",
            status=outcome.status,
            reward=outcome.reward,
            checks=checks,
            reason_code=outcome.reason,
            evidence=refs,
        )
