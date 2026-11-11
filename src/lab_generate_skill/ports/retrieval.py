"""Retrieval execution, evidence transport and trusted qualification are separate.

No default authority. Real verification must establish complete source lineage,
split/exclusion policy, public context qualification, encoder/config identity and
the scoring execution; well-formed stored bytes alone grant no permission.
"""

from typing import Protocol

from lab_generate_skill.domain.bank import BankManifest
from lab_generate_skill.domain.data_scope import SplitManifest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.retrieval import (
    RetrievalQuery,
    RetrievalScope,
    RetrievalResult,
)
from lab_generate_skill.domain.skill import CompactSkill


class SkillRetriever(Protocol):
    def retrieve(
        self, query: RetrievalQuery, scope: RetrievalScope, k: int, op: OperationContext
    ) -> RetrievalResult: ...

    def reconcile(
        self,
        query: RetrievalQuery,
        scope: RetrievalScope,
        k: int,
        execution_ref: EvidenceRef,
        op: OperationContext,
    ) -> RetrievalResult: ...


class RetrievalAdmission(Protocol):
    """Mandatory pre-encoding source/split/context/operation qualification.

    Verify full policy and real provenance; no default allow implementation. This
    hook must not encode, mutate websites or broaden source/paid authorization.
    Cleanup may reconcile recorded evidence but never start encoding.
    """

    def admit(
        self,
        query: RetrievalQuery,
        scope: RetrievalScope,
        bank: BankManifest,
        split: SplitManifest,
        op: OperationContext,
    ) -> None: ...


class RetrievalAuthority(Protocol):
    def verify(
        self,
        result: RetrievalResult,
        bank: BankManifest,
        split: SplitManifest,
        op: OperationContext,
    ) -> None: ...


class RetrievalRecords(Protocol):
    def publish(self, result: RetrievalResult, op: OperationContext) -> EvidenceRef: ...
    def load(
        self,
        reference: EvidenceRef,
        query: RetrievalQuery,
        scope: RetrievalScope,
        op: OperationContext,
    ) -> tuple[CompactSkill, ...]: ...
