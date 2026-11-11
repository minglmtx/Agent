"""Consume retrieval against a frozen construction scope and public task goal.

Never infer expected scope/query from the result under verification. The actual
RetrievalRecords implementation checks full lineage/scoring and authority; this
consumer validates its returned public skills before Generator input comparison.
"""

from pydantic import TypeAdapter
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.domain.construction import ConstructionPlan
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.retrieval import RetrievalQuery
from lab_generate_skill.domain.skill import CompactSkill
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.retrieval import RetrievalRecords

_SKILLS = TypeAdapter(tuple[CompactSkill, ...])


class ConstructionRetrievalReader:
    def __init__(self, evidence: EvidenceReader, records: RetrievalRecords) -> None:
        self.reads, self.records = StateReads(evidence), records

    def load(
        self, plan: ConstructionPlan, op: OperationContext, control: OperationControl
    ) -> tuple[CompactSkill, ...]:
        context = self.reads.parse(
            plan.public_context_ref,
            "public-construction-context/1",
            PublicConstructionContext,
            control,
            visibility="public",
        )
        if context.task.identity != plan.task.identity:
            raise OwnershipConflict("Retrieval query must retain the planned task")
        query = RetrievalQuery(
            task=plan.task.identity,
            literal_goal=context.task.goal,
            public_context_ref=plan.public_context_ref,
        )
        skills = _SKILLS.validate_python(
            self.records.load(plan.retrieval_ref, query, plan.retrieval_scope, op),
            strict=True,
        )
        if len(skills) != plan.method.top_k:
            raise ValueError(
                "Retrieval consumer requires exactly the frozen top-k skills"
            )
        control.checkpoint()
        return skills
