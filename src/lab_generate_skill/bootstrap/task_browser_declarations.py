"""Late actual prepared browser declarations with explicit site codec; no worker effects.

Only immutable installation/assets are taken from the supplied template. Task,
scope, native preparation and Actor settings come from the current original
source/claim/RunPlan and measured preparation. No predicted observation or
baseline, test permission or model/browser substitute is supplied here.
"""

from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from lab_generate_skill.adapters.models.actor_execution_scope import ActorExecutionScope
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.browser_step import BrowserSlurmBinding
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.errors import OwnershipConflict, DispatchAlreadyCommitted
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.lifecycle import OperationContext
from collections.abc import Callable
from lab_generate_skill.domain.browser_initialization import BrowserInitialization
from lab_generate_skill.domain.validation import Identifier
from pydantic import TypeAdapter
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.task_initialization import (
    TaskInitializationPlan,
    TaskActorInitialization,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from .owned_task_execution import TaskBrowserDeclarations


class OriginalTaskBrowserDeclarations:
    def __init__(
        self,
        owner: ClaimedRunResourceOwner,
        model: ActorExecutionScope,
        reset: ResetPlan,
        template: BrowserWorkerConfiguration,
        actor: TaskActorInitialization,
        *,
        initialization: Callable[
            [RecordedSiteTaskPreparation, EvidenceRef, EvidenceRef, OperationControl],
            BrowserInitialization,
        ],
        producer: str,
    ) -> None:
        if not isinstance(owner, ClaimedRunResourceOwner) or not isinstance(
            model, ActorExecutionScope
        ):
            raise TypeError("Original claimed owner and actual acquired model required")
        self.owner, self.model = owner, model
        self.reset, self.template, self.actor = (
            ResetPlan.model_validate(reset),
            BrowserWorkerConfiguration.model_validate(template),
            TaskActorInitialization.model_validate(actor),
        )
        if not callable(initialization):
            raise TypeError(
                "Explicit original site browser initialization codec required"
            )
        self.initialization = initialization
        self.producer = TypeAdapter(Identifier).validate_python(producer, strict=True)
        self.attempted = False
        if (
            self.reset.scope.owner != owner.run.owner
            or self.reset.scope.task != owner.task.identity
            or self.reset.scope.attempt_id != owner.task_plan.intent.binding.attempt_id
            or len(self.reset.attempt_allocations) != 1
            or self.actor.model_allocation != model.binding.resource
        ):
            raise OwnershipConflict(
                "Browser settings changed original task/model/reset"
            )

    def __call__(
        self,
        prep: RecordedSiteTaskPreparation,
        operation: OperationContext,
        control: OperationControl,
    ) -> TaskBrowserDeclarations:
        if self.attempted:
            raise DispatchAlreadyCommitted(
                "Original browser declarations already attempted"
            )
        self.owner.caller(operation, control)
        self.attempted = True
        phase = self.owner.task_source(operation, control)
        self.model.require_original(
            self.model.binding,
            operation.model_copy(
                update={
                    "allocation_id": self.model.spec.token.allocation_id,
                    "recovery_ref": self.model.spec.token.recovery_ref,
                }
            ),
            control,
            live=True,
        )
        state = prep.state
        prepared, prepared_ref = state.result, state.result_ref
        if (
            prep.plan != self.owner.task_plan
            or prep.declaration.scope != self.reset.scope
            or prepared is None
            or prepared_ref is None
            or state.prepare_request is None
            or prepared.scope != self.reset.scope
            or prep.site.site.instance.files != prep.spec.configuration.files
            or prep.spec.configuration.installation != self.template.installation
        ):
            raise OwnershipConflict(
                "Actual original preparation/site/installation required"
            )
        acquired = state.original_acquired()
        public = self.owner.reads.parse(
            phase.task.public_task_ref,
            "public-task/1",
            PublicTask,
            control,
            visibility="public",
        )
        site = prep.site.site
        session = BrowserSessionSpec(
            scope=self.reset.scope,
            task=public,
            chromium_executable=self.template.spec.chromium_executable,
            seed=self.template.spec.seed,
            action_timeout_ms=self.template.spec.action_timeout_ms,
            requirements=self.template.spec.requirements,
            max_events=self.template.spec.max_events,
        )
        cfg = BrowserWorkerConfiguration(
            spec=session,
            initialization=self.initialization(
                prep,
                prepared.publication.prepared_ref,
                acquired.site_started_ref,
                control,
            ),
            installation=self.template.installation,
            playwright_browsers_path=self.template.playwright_browsers_path,
            library_directories=self.template.library_directories,
        )
        spec = BrowserResourceSpec(
            token=self.reset.attempt_allocations[0],
            configuration=cfg,
            slurm=BrowserSlurmBinding(
                execution=prep.spec.slurm.execution,
                parent=prep.spec.slurm.parent,
                srun_executable=prep.spec.slurm.srun_executable,
                scontrol_executable=prep.spec.slurm.scontrol_executable,
            ),
        )
        token = spec.token
        op = OperationContext.model_validate(
            {
                **operation.model_dump(),
                "operation_id": self.owner.task_plan.operation.operation_id
                + ".browser-acquire",
                "allocation_id": token.allocation_id,
                "recovery_ref": token.recovery_ref,
            }
        )

        def phase_op(name: str) -> OperationContext:
            return operation.model_copy(
                update={
                    "operation_id": self.owner.task_plan.operation.operation_id
                    + ".initial-"
                    + name,
                }
            )

        d = TaskInitializationPlan(
            scope=self.reset.scope,
            prepared_result_ref=prepared_ref,
            source_context_receipt_ref=phase.context_receipt_ref,
            browser_spec_ref=self._put(
                spec.model_dump_json().encode(), spec.schema_version, control
            ),
            browser_acquisition=op,
            capture_operation=op.model_copy(
                update={
                    "operation_id": self.owner.task_plan.operation.operation_id
                    + ".initial-capture"
                }
            ),
            initial_operation=phase_op("checks"),
            baseline_operation=phase_op("baseline"),
            comparison_operation=phase_op("compare"),
            equivalence_operation=phase_op("equivalence"),
            actor=self.actor,
        )
        return TaskBrowserDeclarations(
            spec, d, self._put(d.model_dump_json().encode(), d.schema_version, control)
        )

    def _put(self, raw: bytes, schema: str, control: OperationControl) -> EvidenceRef:
        metadata = EvidenceMetadata(
            media_type="application/json",
            content_schema=schema,
            visibility="private",
            producer=self.producer,
        )
        ref = self.owner.evidence.put(raw, metadata, control=control)
        if ref != evidence_reference(raw, metadata):
            raise OwnershipConflict(
                "Browser declaration publication changed original bytes"
            )
        return ref
