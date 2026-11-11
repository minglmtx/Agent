"""One public Generator input rule for registration and pre-inference checks."""

from lab_generate_skill.domain.construction import ConstructionCall, ConstructionPlan
from lab_generate_skill.domain.construction_inputs import (
    GenerationInput,
    PublicConstructionContext,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from .construction_retrieval import ConstructionRetrievalReader
from .state_reads import StateReads
from .construction_actor_capabilities import selected_actor_capabilities
from lab_generate_skill.domain.construction_preparation import (
    ConstructionGenerationSource,
)
from lab_generate_skill.domain.local_generator import LocalGeneratorBaseParameters
from lab_generate_skill.domain.task import PublicTask


class ConstructionGenerationReader:
    def __init__(
        self, evidence: EvidenceReader, retrieval: ConstructionRetrievalReader
    ) -> None:
        self.reads, self.retrieval = StateReads(evidence), retrieval

    def prepare(
        self, plan: ConstructionPlan, op: OperationContext, control: OperationControl
    ) -> ConstructionGenerationSource:
        context = self.reads.parse(
            plan.public_context_ref,
            "public-construction-context/1",
            PublicConstructionContext,
            control,
            visibility="public",
        )
        model = next(m for m in plan.models if m.role == "generator")
        public = self.reads.parse(
            plan.task.public_task_ref,
            "public-task/1",
            PublicTask,
            control,
            visibility="public",
        )
        if (
            context.task != public
            or context.task.identity != plan.task.identity
            or model.paid
        ):
            raise OwnershipConflict("Original public task and local Generator required")
        skills = self.retrieval.load(plan, op, control)
        base = self.reads.parse(
            model.parameters_ref,
            "model-parameters/1",
            LocalGeneratorBaseParameters,
            control,
        )
        return ConstructionGenerationSource(
            context=context,
            skills=skills,
            base=base,
            actor_capabilities=selected_actor_capabilities(plan, self.reads, control),
        )

    def load(
        self,
        plan: ConstructionPlan,
        call: ConstructionCall,
        op: OperationContext,
        control: OperationControl,
    ) -> GenerationInput:
        if call.role != "generator":
            raise OwnershipConflict("Generator input reader rejects other roles")
        expected_schema = (
            "generation-input/2"
            if plan.actor_context_configuration_ref is not None
            else "generation-input/1"
        )
        if call.input_ref.content_schema != expected_schema:
            raise OwnershipConflict(
                "Generator input version differs from selected construction Actor configuration"
            )
        skills = self.retrieval.load(plan, op, control)
        request = self.reads.parse(
            call.input_ref,
            expected_schema,
            GenerationInput,
            control,
            visibility="public",
        )
        self.reads.dependencies((request,), control)
        context = self.reads.parse(
            plan.public_context_ref,
            "public-construction-context/1",
            PublicConstructionContext,
            control,
            visibility="public",
        )
        if (
            request.context != context
            or request.actor_capabilities
            != selected_actor_capabilities(plan, self.reads, control)
            or request.retrieved_skills != skills
            or (
                request.request_id,
                request.candidate_index,
                request.resample_index,
                request.seed,
                request.temperature,
            )
            != (
                call.request_id,
                call.candidate_slot,
                call.resample_index,
                call.seed,
                call.temperature,
            )
        ):
            raise OwnershipConflict(
                "Actual Generator input differs from registered call"
            )
        return request
