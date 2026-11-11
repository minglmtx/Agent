"""Collect only the declared Map state-check graph, without opening native files.

Original parent checks retain all semantic and physical-file obligations. This
collector cannot publish, execute, restore or traverse arbitrary JSON fields.
"""

from typing import TypeVar
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.map_state_inputs import (
    MapStateInputBody,
    MapStateInputBodies,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.domain.state_qualification import (
    EnvironmentSelection,
    ResetSelection,
)
from lab_generate_skill.domain.state_checks import InitialStateSpec
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_resume import (
    SiteResumeRequest,
    SiteResumeResult,
    SiteResumeIntent,
)
from lab_generate_skill.domain.lifecycle import RecoveryPlan, ClosureReceipt
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.tasks.state_codec import MapTaskStateCodec
from lab_generate_skill.adapters.processes.wire_json import json_object

T = TypeVar("T", bound=Contract)


class MapStateInputCollector:
    def __init__(self, reader: EvidenceReader, control: OperationControl) -> None:
        self.reader, self.control = reader, control
        self.bodies: dict[EvidenceRef, MapStateInputBody] = {}

    def body(self, reference: EvidenceRef, schema: str) -> bytes:
        private_state_ref(reference, schema)
        self.control.checkpoint()
        if reference not in self.bodies:
            body = MapStateInputBody(
                reference=reference,
                text=self.reader.read(reference, self.control).decode(),
            )
            self.bodies[reference] = body
            MapStateInputBodies(bodies=tuple(self.bodies.values()))
        return self.bodies[reference].text.encode()

    def read(self, reference: EvidenceRef, schema: str, model: type[T]) -> T:
        raw = self.body(reference, schema)
        json_object(raw)
        return model.model_validate_json(raw)

    def environment(self, selection: EnvironmentSelection, task: TaskIdentity) -> None:
        if selection.scope.task != task:
            raise OwnershipConflict("Map state graph changed original task")
        self.read(selection.spec_ref, "initial-state-spec/1", InitialStateSpec)
        site = self.read(
            selection.site_spec_ref, "site-resource-spec/1", SiteResourceSpec
        )
        inputs = site.configuration.map_inputs
        if (
            not isinstance(inputs, MapNavigationWorkerInputs)
            or inputs.scope != selection.scope
        ):
            raise OwnershipConflict("Map state graph changed configured scope")
        started = self.read(
            selection.site_started_ref, "site-resource-started/1", SiteResourceStarted
        )
        start = json_object(self.body(started.evidence, "site-resource-fact/1"))
        details = start.get("details")
        if not isinstance(details, dict) or "ready_ref" not in details:
            raise OwnershipConflict("Original Map startup ready reference required")
        ready = EvidenceRef.model_validate(details["ready_ref"])
        self.body(ready, "site-resource-fact/1")
        codec = MapTaskStateCodec(task)
        snapshot = self.read(
            selection.snapshot_ref, codec.snapshot_schema, codec.snapshot_type
        )
        binding = self.read(snapshot.request.binding_ref, "task-binding/1", TaskBinding)
        self.read(binding.private_spec_ref, codec.private_schema, codec.private_type)
        self.read(site.token.recovery_ref, "recovery-plan/1", RecoveryPlan)

    def collect(
        self,
        selection: EnvironmentSelection | ResetSelection,
        reference: EvidenceRef,
        task: TaskIdentity,
    ) -> MapStateInputBodies:
        actual = self.read(reference, selection.schema_version, type(selection))
        if actual != selection:
            raise OwnershipConflict("Map state graph changed selected root bytes")
        if isinstance(selection, EnvironmentSelection):
            self.environment(selection, task)
        else:
            env = self.read(
                selection.environment_selection_ref,
                "environment-selection/1",
                EnvironmentSelection,
            )
            self.environment(env, task)
            plan = self.read(selection.plan_ref, "reset-plan/1", ResetPlan)
            if plan.scope.task != task:
                raise OwnershipConflict("Map state graph changed original Reset task")
            for ref in selection.closure_refs:
                self.read(ref, "closure-receipt/1", ClosureReceipt)
            self.read(
                selection.restore_request_ref, "site-task-request/2", SiteTaskRequest
            )
            self.read(
                selection.restore_result_ref, "site-task-result/1", SiteTaskResult
            )
            self.read(
                selection.resume_request_ref, "site-resume-request/1", SiteResumeRequest
            )
            self.read(
                selection.resume_result_ref, "site-resume-result/1", SiteResumeResult
            )
            self.read(
                selection.resume_intent_ref, "site-resume-intent/1", SiteResumeIntent
            )
            self.read(plan.task_recovery_ref, "recovery-plan/1", RecoveryPlan)
        self.control.checkpoint()
        return MapStateInputBodies(bodies=tuple(self.bodies.values()))
