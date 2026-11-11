"""Selected actual Map preparation on existing task-binding and preparation ports."""

from collections.abc import Callable
from lab_generate_skill.bootstrap.deferred_state_records import (
    DeferredPreparationRecords,
)
import hashlib
from typing import Any
from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.bootstrap.map_native_overlay import load_overlay_inputs
from lab_generate_skill.bootstrap.map_overlay_records import map_preparation_records
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import RecoveryPlan, OperationContext
from lab_generate_skill.domain.site_worker import SiteInstanceStarted
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.tasks.overlay_policy import overlay_initial_spec
from site_preparation_native import NativePreparation
from site_resource_fixtures import Case
from map_source_inputs import MapSourceInputs, public_task
from lab_generate_skill.sites.map.tasks.navigation_spec import NavigationSpec
from lab_generate_skill.sites.map.tasks.state_policy import map_initial_spec
from lab_generate_skill.sites.map.tasks.state_codec import MapTaskStateCodec
from test_slurm_commands import guard


class MapPreparation(NativePreparation):
    def __init__(
        self,
        c: Case,
        started: SiteInstanceStarted | None,
        inputs: MapSourceInputs,
        *,
        allowed_actions: tuple[str, ...],
        declared_endpoint: str | None = None,
        actual_instance: Callable[[], SiteInstanceStarted] | None = None,
    ) -> None:
        self.c = c
        self.inputs = inputs
        self.request = None
        self.result = None
        self.environment = None
        cfg = inputs.configuration
        if (
            c.spec.configuration != cfg
            or (started is not None and started.files != cfg.files)
            or cfg.map_inputs is None
        ):
            raise ValueError("Original selected Map site/source declaration required")
        self.scope = cfg.map_inputs.scope
        self.attempt_id, self.context_id = self.scope.attempt_id, self.scope.context_id
        endpoint = started.endpoint if started is not None else declared_endpoint
        if endpoint is None or (started is None and actual_instance is None):
            raise ValueError(
                "Declared original public origin and actual instance supplier required"
            )
        self.public = inputs.public_at(endpoint, allowed_actions)
        if self.public.identity != self.scope.task:
            raise ValueError("Original Map public source changed configured task scope")
        self.overlay_spec = inputs.private
        if (
            hashlib.sha256(self.private_input_json().encode()).hexdigest()
            != cfg.map_inputs.private_input_sha256
        ):
            raise ValueError("Original Map source input pin changed")
        raw = c.evidence.read(self.native_contract_ref, control=guard(10))
        if isinstance(self.overlay_spec, NavigationSpec):
            if inputs.selection is None:
                raise ValueError("Explicit original navigation selection required")
            original = inputs.selection.load(self.native_contract_ref, self.public)
            matches = original == self.overlay_spec and raw == inputs.selection.native
        else:
            matches = (
                load_overlay_inputs(
                    raw, self.native_contract_ref, self.public
                ).private_spec
                == self.overlay_spec
            )
        if not matches:
            raise ValueError("Original selected Map contract changed")
        self.spec = map_initial_spec(
            self.public.identity, self.native_contract_ref.sha256
        )
        self.spec_ref = inputs.state_spec_ref
        if (
            c.evidence.read(self.spec_ref, control=guard(10))
            != self.spec.model_dump_json().encode()
        ):
            raise ValueError("Original Map complete baseline declaration changed")
        self.binding = TaskBinding(
            identity=self.public.identity,
            registration_id=(
                "engineering-map-navigation-page"
                if isinstance(self.overlay_spec, NavigationSpec)
                else "engineering-map-route-overlay"
            ),
            public_task_ref=self.put(self.public, "public"),
            private_spec_ref=self.put(self.overlay_spec),
            baseline_ref=self.spec_ref,
        )
        self.bindings = EvidenceTaskBindings(c.evidence, c.controls, self)
        self.binding_ref = self.bindings.publish(self.binding, c.op)
        self.recovery = RecoveryPlan(
            recovery_id="selected-map-task-recovery",
            owner=self.scope.owner,
            attempt_id=self.attempt_id,
            baseline_ref=self.spec_ref,
            restore_component_id=MapTaskStateCodec(
                self.public.identity
            ).recovery_component,
            restore_component_version="1",
            state_coverage=self.spec.task_reset_checks,
        )
        self.recovery_ref = self.put(self.recovery)
        if started is not None:
            self.records = map_preparation_records(
                c.evidence, c.controls, self.bindings, self, cfg, started
            )
        else:
            assert actual_instance is not None
            self.records = DeferredPreparationRecords(
                lambda: map_preparation_records(
                    c.evidence, c.controls, self.bindings, self, cfg, actual_instance()
                )
            )

    @property
    def native_contract_ref(self) -> EvidenceRef:
        return self.overlay_spec.native_contract_ref

    def private_input_json(self) -> str:
        return self.overlay_spec.model_dump_json()

    def verify_binding(
        self,
        binding: TaskBinding,
        public_task: PublicTask,
        private_spec: bytes,
        baseline: bytes,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if (
            binding != self.binding
            or public_task != self.public
            or private_spec != self.private_input_json().encode()
            or baseline != self.spec.model_dump_json().encode()
        ):
            raise ValueError(
                "Original selected Map public/private/baseline binding changed"
            )

    def publish(
        self,
        request: SiteTaskRequest,
        result: SiteTaskResult,
        started: SiteInstanceStarted,
        *,
        environment: EnvironmentBaseline | None = None,
    ) -> dict[str, Any]:
        if (
            environment is None
            or environment.scope != self.scope
            or environment.checks.status != "pass"
        ):
            raise ValueError(
                "Actual qualified complete Map environment required before preparation publication"
            )
        return super().publish(request, result, started, environment=environment)
