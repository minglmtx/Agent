"""Original preparation producer hands four exact declaration bodies forward.

Only its first physical declaration read may prime this carrier. Consumers never
build missing bodies. The existing one-shot task scope and current source/store
gate remain mandatory; neither permissions nor effects are retained here.
"""

from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_preparation import SiteTaskPreparationPlan
from lab_generate_skill.ports.contexts import ContextCurrentChecks
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.preparation_record_inputs import PreparationRecordScope
from lab_generate_skill.ports.task_preparation_inputs import PreparationDeclarationFacts
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from lab_generate_skill.policies.task_preparation import require_declared_preparation


class TaskPreparationDeclarationInputs:
    def __init__(
        self,
        plan: TaskExecutionPlan,
        declaration: SiteTaskPreparationPlan,
        scope: PreparationRecordScope,
        current: ContextCurrentChecks,
    ) -> None:
        self.plan, self.declaration = plan, declaration
        self.scope, self.current = scope, current
        self.facts: PreparationDeclarationFacts | None = None
        self._verified_facts: PreparationDeclarationFacts | None = None
        self.statistics = {
            "declaration_graph_reads": 0,
            "declaration_graph_reuses": 0,
            "declaration_integrity_checks": 0,
        }

    def _check(
        self,
        plan: TaskExecutionPlan,
        declaration: SiteTaskPreparationPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self.scope.check(operation, control)
        if (
            plan != self.plan
            or declaration != self.declaration
            or self.scope.task_identity != plan.intent.binding.task
        ):
            raise OwnershipConflict(
                "Preparation bodies changed their original declarations"
            )
        self.current.check_context_current(operation, control)
        self.scope.check(operation, control)

    def _integrity(self, facts: PreparationDeclarationFacts) -> None:
        self.statistics["declaration_integrity_checks"] += 1
        plan, d = self.plan, self.declaration
        if facts.declaration != d:
            raise OwnershipConflict("Preparation declaration body changed")
        for reference, value in (
            (plan.declaration_ref, facts.declaration),
            (d.site_spec_ref, facts.site),
            (plan.reset_plan_ref, facts.reset),
            (d.task_binding_ref, facts.binding),
        ):
            if (
                reference.content_schema,
                reference.visibility,
                reference.media_type,
            ) != (
                value.schema_version,
                "private",
                "application/json",
            ):
                raise OwnershipConflict(
                    "Preparation declaration reference changed role/schema"
                )
            require_complete_bytes(reference, value.model_dump_json().encode())
        require_declared_preparation(plan, d, facts.reset, facts.site, facts.binding)

    def lookup(
        self,
        plan: TaskExecutionPlan,
        declaration: SiteTaskPreparationPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> PreparationDeclarationFacts | None:
        self._check(plan, declaration, operation, control)
        facts = self.facts
        if facts is not None:
            # Frozen contracts and the frozen tuple are the exact objects the
            # producer verified. Changed/replaced bodies are never adopted.
            if facts is not self._verified_facts:
                self._integrity(facts)
                raise OwnershipConflict("Original verified preparation bodies replaced")
            self.statistics["declaration_graph_reuses"] += 1
        return facts

    def record(
        self,
        plan: TaskExecutionPlan,
        facts: PreparationDeclarationFacts,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self._check(plan, facts.declaration, operation, control)
        if self.facts is not None or self.statistics["declaration_graph_reads"]:
            raise OwnershipConflict(
                "Preparation producer declaration read already retained"
            )
        self._integrity(facts)
        self.facts = self._verified_facts = facts
        self.statistics["declaration_graph_reads"] += 1

    def require(
        self,
        plan: TaskExecutionPlan,
        declaration: SiteTaskPreparationPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> PreparationDeclarationFacts:
        facts = self.lookup(plan, declaration, operation, control)
        if facts is None:
            raise OwnershipConflict(
                "Original producer declaration readback is missing; no consumer rebuild"
            )
        return facts

    def clear(self) -> None:
        self.facts = None
        self._verified_facts = None
