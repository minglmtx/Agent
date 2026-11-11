"""Current native navigation permissions from the original task producers/CAS.

No dispatch, persisted permission cache, alternate intent ledger or test registry.
Original current source/claim/physical gates remain mandatory through the actual
preparation/finalization authorities. Owner-local state only identifies which
original intent is currently awaiting its single fixed-client dispatch.
"""

import os
import threading
from uuid import uuid4
from typing import TypeVar
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.adapters.sites.task_finalization import RecordedTaskFinalization
from lab_generate_skill.domain.errors import OwnershipConflict, RevisionConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import RecoveryPlan, ResourceRecord
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.site_resource import (
    SiteResourceStarted,
    SiteResourceSpec,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_site_acquisition import SiteTaskAcquired
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.site_tasks import SiteTaskInputChecks

T = TypeVar("T", bound=Contract)


class OriginalTaskNativeAuthority:
    def __init__(
        self,
        plan: TaskExecutionPlan,
        preparation: RecordedSiteTaskPreparation,
        finalization: RecordedTaskFinalization,
        inputs: SiteTaskInputChecks,
    ) -> None:
        self.plan = TaskExecutionPlan.model_validate(plan)
        if preparation is None or finalization is None or inputs is None:
            raise ValueError(
                "Original preparation/finalization and source gates required"
            )
        if (
            preparation.plan != plan
            or finalization.plan != plan
            or finalization.preparation is not preparation
        ):
            raise OwnershipConflict("Native authority changed original task producers")
        self.preparation, self.finalization = preparation, finalization
        self.inputs = inputs
        self.owner = os.getpid(), threading.get_ident()

    def _parse(
        self,
        reference: EvidenceRef,
        schema: str,
        model: type[T],
        control: OperationControl,
    ) -> T:
        if (reference.content_schema, reference.media_type, reference.visibility) != (
            schema,
            "application/json",
            "private",
        ):
            raise OwnershipConflict(
                "Original native source evidence schema/visibility changed"
            )
        return model.model_validate_json(self.preparation.io.read(reference, control))

    def _selected(self, request: SiteTaskRequest) -> tuple[EvidenceRef, str]:
        p, f = self.preparation, self.finalization
        s = p.state
        if request.action == "snapshot":
            original, reference = s.snapshot_request, s.snapshot_request_ref
            eligible = s.phase == "preparing" and s.snapshot_result is None
            producer = "task-preparation-v1"
        elif request.action == "prepare":
            original, reference = s.prepare_request, s.prepare_request_ref
            eligible = (
                s.phase == "preparing"
                and s.prepare_result is None
                and s.snapshot_result_ref is not None
                and s.environment_ref is not None
            )
            producer = "task-preparation-v1"
        elif request.action == "restore":
            original, reference = f.state.restore_request, f.state.restore_request_ref
            eligible = (
                f.state.phase == "restoring"
                and f.state.closed is not None
                and f.state.restore_result is None
            )
            producer = "task-finalization-v1"
        else:
            raise OwnershipConflict(
                "Only original current snapshot/prepare/restore source calls supported"
            )
        if not eligible or original != request or reference is None:
            raise OwnershipConflict("Original native request is not awaiting dispatch")
        if (
            reference.content_schema,
            reference.visibility,
            reference.media_type,
            reference.producer,
        ) != (request.schema_version, "private", "application/json", producer):
            raise OwnershipConflict("Native task intent lost original producer/role")
        return reference, producer

    def _resource(
        self, request: SiteTaskRequest, control: OperationControl
    ) -> ResourceRecord:
        p, cfg = self.preparation, self.preparation.spec.configuration
        read = request.operation.model_copy(
            update={
                "operation_id": "native-source-read-" + uuid4().hex,
                "parent_operation_id": p.declaration.resource_read_operation.parent_operation_id,
                "mode": "cleanup",
                "attempt_id": None,
                "allocation_id": cfg.token.allocation_id,
                "recovery_ref": cfg.token.recovery_ref,
                "cancellation_ref": None,
            }
        )
        control.checkpoint()
        record = ResourceRecord.model_validate(p.resources.read(cfg.token, read))
        if (
            record.token != cfg.token
            or record.state != "acquired"
            or len(record.events) < 3
            or len(record.events[1].evidence) != 1
        ):
            raise OwnershipConflict("Native task requires original acquired site")
        acquisition = self._parse(
            record.events[1].evidence[0],
            "resource-acquisition-intent/1",
            ResourceAcquisitionIntent,
            control,
        )
        spec = (
            p.declared_inputs.require(
                self.plan, p.declaration, request.operation, control
            ).site
            if p.declared_inputs is not None
            else self._parse(
                p.declaration.site_spec_ref,
                "site-resource-spec/1",
                SiteResourceSpec,
                control,
            )
        )
        if p.state.acquired_ref is None:
            raise OwnershipConflict("Original saved acquiring binding required")
        bound = self._parse(
            p.state.acquired_ref, "site-task-acquired/1", SiteTaskAcquired, control
        )
        if (
            bound != p.state.original_acquired()
            or bound.declaration_ref != self.plan.declaration_ref
            or bound.resource_intent_ref != record.events[1].evidence[0]
            or bound.resource_acquired_ref != record.events[2].evidence[0]
        ):
            raise OwnershipConflict("Native source changed original acquired binding")
        started = self._parse(
            bound.site_started_ref,
            "site-resource-started/1",
            SiteResourceStarted,
            control,
        )
        if (
            acquisition.token != cfg.token
            or acquisition.configuration_ref != p.declaration.site_spec_ref
            or acquisition.operation.operation_id
            != p.declaration.resource_read_operation.parent_operation_id
            or spec != p.spec
            or started != p.site.site
            or started.instance.files != cfg.files
        ):
            raise OwnershipConflict(
                "Native source changed original acquisition/site bytes"
            )
        control.checkpoint()
        return record

    def verify_task(
        self,
        configuration: SiteWorkerConfiguration,
        request: SiteTaskRequest,
        control: OperationControl,
    ) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Native task authority changed owner context")
        p, f = self.preparation, self.finalization
        request = SiteTaskRequest.model_validate(request)
        if configuration != p.spec.configuration:
            raise OwnershipConflict("Native authority changed frozen configuration")
        reference, producer = self._selected(request)
        control.checkpoint()
        if p.io.read(reference, control) != request.model_dump_json().encode():
            raise OwnershipConflict(
                "Native request differs from original persisted bytes"
            )
        binding = (
            p.declared_inputs.require(
                self.plan, p.declaration, request.operation, control
            ).binding
            if p.declared_inputs is not None
            else self._parse(
                p.declaration.task_binding_ref, "task-binding/1", TaskBinding, control
            )
        )
        private = p.io.read(p.declaration.private_input_ref, control)
        # Both immutable objects are checked. The mandatory site codec verifies
        # their exact canonical relation (direct Map input or Admin envelope).
        if binding.private_spec_ref != p.declaration.private_input_ref:
            p.io.read(binding.private_spec_ref, control)
        if (
            request.binding_ref != p.declaration.task_binding_ref
            or private != request.private_input.encode()
            or request.operation.recovery_ref != f.reset.task_recovery_ref
        ):
            raise OwnershipConflict(
                "Native request changed original binding/input/recovery"
            )
        recovery = self._parse(
            f.reset.task_recovery_ref, "recovery-plan/1", RecoveryPlan, control
        )
        environment = self._parse(
            configuration.token.recovery_ref, "recovery-plan/1", RecoveryPlan, control
        )
        snapshot_bytes: bytes | None = None
        if request.action != "snapshot":
            if (
                request.snapshot_ref is None
                or request.snapshot_ref != p.state.snapshot_ref
            ):
                raise OwnershipConflict(
                    "Original complete native snapshot reference required"
                )
            if (
                request.snapshot_ref.content_schema,
                request.snapshot_ref.media_type,
                request.snapshot_ref.visibility,
            ) != (p.declaration.snapshot_schema, "application/json", "private"):
                raise OwnershipConflict(
                    "Original native snapshot schema/visibility changed"
                )
            snapshot_bytes = p.io.read(request.snapshot_ref, control)
        self.inputs.verify_inputs(
            configuration,
            request,
            binding,
            recovery,
            environment,
            snapshot_bytes,
            None if request.action == "snapshot" else p.state.snapshot_request,
            control,
        )
        before = self._resource(request, control)
        if request.action == "restore":
            f.authority.verify(
                self.plan,
                f.declaration,
                tuple(
                    dict.fromkeys(
                        (
                            *p.state.references,
                            *f.state.references,
                            *f.browser.references,
                        )
                    )
                ),
                request.operation,
                control,
            )
        else:
            p.authority.verify(self.plan, p.declaration, request.operation, control)
        if (
            self._selected(request) != (reference, producer)
            or self._resource(request, control) != before
        ):
            raise RevisionConflict(
                "Original native task/resource changed during admission"
            )
        control.checkpoint()
