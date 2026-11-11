"""Real current journals/claim; synthetic physical/native cleanup permission."""

from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.application.construction_task_phases import (
    ConstructionTaskFinalizationAuthority,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_finalization import TaskFinalizationPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from task_execution_fixtures import TaskCase, task_case
from test_task_preparation_admission import declaration as preparation_declaration
from construction_storage_fixtures import put


class UnitCleanupSource:
    def __init__(self) -> None:
        self.denied = False
        self.calls: list[OperationContext] = []

    def verify(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskFinalizationPlan,
        references: tuple[EvidenceRef, ...],
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.calls.append(operation)
        if self.denied:
            raise PermissionError("Synthetic original native cleanup permission denied")
        assert declaration.scope.task == plan.intent.binding.task
        assert operation.mode == "cleanup"


@dataclass
class CleanupAdmissionCase:
    task: TaskCase
    declaration: TaskFinalizationPlan
    bridge: ConstructionTaskFinalizationAuthority
    source: UnitCleanupSource


def cleanup_case(root: Path) -> CleanupAdmissionCase:
    c = task_case(root)
    declaration = preparation_declaration(c)
    c.plan = c.plan.model_copy(
        update={
            "declaration_ref": put(
                c.admission.data.store, declaration, declaration.schema_version
            )
        }
    )
    d = TaskFinalizationPlan(
        scope=c.phases.closed.reset_plan.scope,
        browser_close_operation_id="original-browser-close",
        restore_operation_id="original-native-restore",
        resume_operation_id="original-native-resume",
        qualification_operation_id="original-reset-facts",
        reset_operation_id="original-safe-reset",
    )
    source = UnitCleanupSource()
    bridge = ConstructionTaskFinalizationAuthority(
        put(c.admission.data.store, d, d.schema_version),
        c.deps.construction,
        c.deps.runs,
        c.deps.admission.claims,
        EvidenceRunPlans(c.deps.evidence, c.deps.controls),
        source,
        c.deps.evidence,
    )
    return CleanupAdmissionCase(c, d, bridge, source)
