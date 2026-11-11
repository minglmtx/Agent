"""Hand original producer bodies to capture admission; never retain permission.

The five exact inputs already belong to this one active owned invocation. Every
read rechecks its producer scope/current context and exact bytes. Other evidence
continues through the original store; source/run/claim/resource gates are intact.
"""

from collections.abc import Callable
from lab_generate_skill.adapters.ledger.resource_facts import ResourceFacts
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.task_capture import TaskCapturePlan
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.initial_observation import InitialObservationReads
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.evidence_bytes import (
    require_complete_bytes,
    require_complete_read_bound,
)
from .task_initialization import RecordedTaskInitialization
from .task_initialization_inputs import TaskInitializationInputs
from .task_preparation import RecordedSiteTaskPreparation


class TaskCaptureAdmissionInputs:
    def __init__(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskCapturePlan,
        declaration_ref: EvidenceRef,
        scope: TaskInitializationInputs,
        preparation: RecordedSiteTaskPreparation,
        initialization: Callable[[], RecordedTaskInitialization],
        initials: InitialObservationReads,
        original: EvidenceStore,
    ) -> None:
        if (
            scope.plan != plan
            or preparation.plan != plan
            or not callable(initialization)
            or initials is None
            or original is None
        ):
            raise OwnershipConflict("Capture bodies require original producers/scope")
        self.plan, self.declaration, self.declaration_ref = (
            plan,
            declaration,
            declaration_ref,
        )
        self.scope, self.preparation = scope, preparation
        self.initialization, self.initials, self.original = (
            initialization,
            initials,
            original,
        )
        self.reads = 0
        self.handoffs = 0

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        reference = EvidenceRef.model_validate(reference)
        self.scope.check(self.plan.operation, control)
        declarations = self.scope.preparation_declarations
        if declarations is None:
            raise OwnershipConflict("Original preparation body handoff is missing")
        facts = declarations.require(
            self.plan, self.preparation.declaration, self.plan.operation, control
        )
        initialized = self.initialization()
        if (
            initialized.plan != self.plan
            or initialized.inputs is not self.scope
            or initialized.state.phase != "initialized"
            or initialized.state.result is None
            or initialized.state.selection is None
            or self.preparation.declaration.task_binding_ref
            != self.plan.evaluation.task_contract_ref
        ):
            raise OwnershipConflict(
                "Capture bodies changed original initialized producer"
            )
        initial = self.initials.load(
            initialized.state.selection, self.plan.operation, control
        )
        actor = initialized.state.result.actor
        if (
            initial.prepared.scope != actor.scope
            or initial.prepared.public_task != actor.task
        ):
            raise OwnershipConflict("Capture bodies changed original task/Actor")
        actor_raw = actor.model_dump_json().encode()
        actor_ref = evidence_reference(
            actor_raw,
            EvidenceMetadata(
                content_schema=actor.schema_version,
                media_type="application/json",
                visibility="private",
                producer="task-execution-v1",
            ),
        )
        bodies = (
            (self.declaration_ref, self.declaration.model_dump_json().encode()),
            (
                self.plan.evaluation.task_contract_ref,
                facts.binding.model_dump_json().encode(),
            ),
            (self.plan.reset_plan_ref, facts.reset.model_dump_json().encode()),
            (
                initial.selection.browser_acquired_ref,
                ResourceFacts.encode(initial.acquired.model_dump(mode="json")),
            ),
            (actor_ref, actor_raw),
        )
        for expected, raw in bodies:
            require_complete_read_bound(
                expected,
                (
                    2 * 1024**2
                    if expected != initial.selection.browser_acquired_ref
                    else 64 * 1024**2
                ),
            )
            require_complete_bytes(expected, raw)
        self.reads += 1
        for expected, raw in bodies:
            if reference == expected:
                self.handoffs += 1
                self.scope.check(self.plan.operation, control)
                return raw
        if any(
            reference.sha256 == ref.sha256
            or reference.content_schema == ref.content_schema
            for ref, _ in bodies
        ):
            raise OwnershipConflict(
                "Capture body changed original full reference or producer"
            )
        return self.original.read(reference, control)

    def put(
        self, data: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        self.scope.check(self.plan.operation, control)
        return self.original.put(data, metadata, control)
