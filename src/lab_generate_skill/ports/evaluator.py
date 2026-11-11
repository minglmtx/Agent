"""Offline evaluator interface; it can read evidence but cannot operate a site.

requirements is consumed by capture preflight. evaluate returns a versioned
judgment; missing facts yield unknown, not failure. The caller independently
checks the returned task/attempt/contract and later reviews sealed evidence.
Every evidence read must receive this same control; an evaluator cannot create
a fresh deadline, call the synchronous file primitive or silently retry I/O.
"""

from typing import Protocol

from lab_generate_skill.domain.evaluation import Evaluation, EvaluationContract
from lab_generate_skill.domain.evidence import EvidenceRequirements

from .evidence import EvidenceReader
from .lifecycle import OperationControl


class Evaluator(Protocol):
    """Site-specific pure judgments share this interface, not success rules."""

    def requirements(self, contract: EvaluationContract) -> EvidenceRequirements: ...

    def evaluate(
        self,
        contract: EvaluationContract,
        evidence: EvidenceReader,
        control: OperationControl,
    ) -> Evaluation: ...
