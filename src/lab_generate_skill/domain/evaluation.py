"""Pure task judgments, separate from execution success and training admission.

Inputs are named checks over captured facts; output preserves unknown as null
reward. No evaluator may turn a missing required fact into a negative reward.
"""

from typing import Literal, Self

from pydantic import Field, model_validator

from .evidence import EvidenceRef, EvidenceRequirements
from .identity import TaskIdentity
from .validation import Contract, Identifier, NonEmptyText


class EvaluationContract(Contract):
    """Attempt binding of a frozen task contract and required evidence.

    task_contract_ref points to the immutable task meaning, not this object itself.
    The evaluator copies that reference and attempt_id into its output; the caller
    checks both. This avoids inferring execution identity from a global context.
    """

    schema_version: Literal["evaluation-contract/1"] = "evaluation-contract/1"
    identity: TaskIdentity
    attempt_id: Identifier
    task_contract_ref: EvidenceRef
    public_task_ref: EvidenceRef
    completion_spec_ref: EvidenceRef
    requirements: EvidenceRequirements
    scope: Literal["benchmark", "local_derived", "engineering"]

    @model_validator(mode="after")
    def public_input_contract(self) -> Self:
        if (
            self.public_task_ref.visibility != "public"
            or self.public_task_ref.content_schema != "public-task/1"
        ):
            raise ValueError("Evaluation must bind the declared public task")
        return self


class CheckResult(Contract):
    """One required completion/protection check with attributable evidence."""

    schema_version: Literal["check-result/1"] = "check-result/1"
    name: Identifier
    status: Literal["pass", "fail", "unknown"]
    reason_code: Identifier
    evidence: tuple[EvidenceRef, ...] = ()


class Evaluation(Contract):
    """Immutable judgment; reward consistency is enforced at every boundary."""

    schema_version: Literal["evaluation/1"] = "evaluation/1"
    identity: TaskIdentity
    attempt_id: Identifier
    contract_ref: EvidenceRef
    evaluator_id: Identifier
    evaluator_version: NonEmptyText
    status: Literal["success", "failure", "unknown"]
    reward: int | None = Field(default=None, ge=0, le=1)
    checks: tuple[CheckResult, ...]
    reason_code: Identifier
    evidence: tuple[EvidenceRef, ...] = ()
    environment_reward: float | None = Field(default=None, allow_inf_nan=False)
    supersedes: EvidenceRef | None = None

    @model_validator(mode="after")
    def consistent_judgment(self) -> Self:
        if len({check.name for check in self.checks}) != len(self.checks):
            raise ValueError("Check names must be unique")
        expected = {"success": 1, "failure": 0, "unknown": None}[self.status]
        if self.reward != expected:
            raise ValueError("Task status and reward disagree")
        if self.status != "unknown":
            if not self.checks or any(
                check.status == "unknown" for check in self.checks
            ):
                raise ValueError("Scored results require complete required checks")
            failed = any(check.status == "fail" for check in self.checks)
            if failed != (self.status == "failure"):
                raise ValueError("Task status disagrees with required checks")
            if any(not check.evidence for check in self.checks):
                raise ValueError("Scored checks require evidence references")
        return self
