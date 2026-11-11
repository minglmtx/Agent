"""Original configured Map environment from startup and complete guard evidence."""

from dataclasses import dataclass
import hashlib
import json
from typing import Any
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.domain.state_checks import InitialStateSpec, StateChecks
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.map_services import MapServiceSpec, MapPorts
from lab_generate_skill.domain.lifecycle import OperationContext, RecoveryPlan
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evaluation import CheckResult
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.map_state_artifacts import MapStateFileReader
from lab_generate_skill.ports.lifecycle import OperationControl
from ..state_reads import MapStateReads
from ..state_rules import object_json
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from .state_codec import MapTaskStateCodec, MapSnapshot
from .state_policy import map_initial_spec


@dataclass(frozen=True)
class MapEnvironmentFacts:
    spec: InitialStateSpec
    site: SiteResourceSpec
    started: SiteResourceStarted
    snapshot: MapSnapshot
    service: MapServiceSpec
    recovery: RecoveryPlan


class OverlayEnvironmentChecks(MapStateReads):
    def __init__(
        self,
        store: EvidenceReader,
        files: MapStateFileReader,
        site: SiteResourceSpec,
        started: SiteResourceStarted,
    ) -> None:
        super().__init__(store, files)
        self.site = SiteResourceSpec.model_validate(site)
        self.started = SiteResourceStarted.model_validate(started)
        if (
            self.site.configuration.site_id != "map"
            or self.site.configuration.map_inputs is None
        ):
            raise OwnershipConflict("Original configured Map environment required")

    @staticmethod
    def checks(
        names: tuple[str, ...], refs: tuple[EvidenceRef, ...], reason: str
    ) -> StateChecks:
        return StateChecks(
            required=names,
            checks=tuple(
                CheckResult(name=name, status="pass", reason_code=reason, evidence=refs)
                for name in names
            ),
        )

    def _fact(self, ref: EvidenceRef, control: OperationControl) -> dict[str, Any]:
        private_state_ref(ref, "site-resource-fact/1")
        if ref.media_type != "application/json":
            raise ValueError("Original Map startup JSON required")
        raw = self.store.read(ref, control=control)
        if (len(raw), hashlib.sha256(raw).hexdigest()) != (ref.size_bytes, ref.sha256):
            raise EvidenceIntegrityError("Original Map startup bytes changed")
        return object_json(raw)

    def _startup(
        self,
        site: SiteResourceSpec,
        started: SiteResourceStarted,
        control: OperationControl,
    ) -> MapServiceSpec:
        cfg = site.configuration
        inputs = cfg.map_inputs
        assert inputs is not None
        instance = started.instance
        if instance.files != cfg.files or len(instance.ports) != 6:
            raise OwnershipConflict("Map startup changed original files/ports")
        service = MapServiceSpec(
            inputs=inputs.runtime,
            ports=MapPorts(
                **dict(
                    zip(
                        ("web", "search", "car", "bike", "foot", "tiles"),
                        instance.ports,
                        strict=True,
                    )
                )
            ),
        )
        ready = started.ready
        installed = ready.worker.installed_sources
        if (
            instance.endpoint != service.endpoint
            or cfg.apptainer != service.apptainer
            or ready.worker.owner_guard.controller != site.slurm.parent.writer
            or (
                ready.controller.target.execution != site.slurm.execution
                or (
                    installed.release_id,
                    installed.manifest_sha256,
                    installed.executable,
                )
                != (
                    cfg.installation.manifest.release_id,
                    cfg.installation.manifest_ref.sha256,
                    cfg.installation.python_executable,
                )
            )
        ):
            raise OwnershipConflict(
                "Map environment changed original worker/release/instance"
            )
        start = self._fact(started.evidence, control)
        details = start.get("details")
        if (
            not isinstance(details, dict)
            or set(details) != {"ready_ref", "started"}
            or details["started"] != instance.model_dump(mode="json")
        ):
            raise OwnershipConflict("Original Map startup details changed")
        acquired_ref = EvidenceRef.model_validate_json(json.dumps(details["ready_ref"]))
        acquired = self._fact(acquired_ref, control)
        digest = hashlib.sha256(site.model_dump_json().encode()).hexdigest()
        for fact in (start, acquired):
            if (
                fact.get("schema_version"),
                fact.get("spec_sha256"),
                fact.get("token"),
                fact.get("state"),
            ) != (
                "site-resource-fact/1",
                digest,
                site.token.model_dump(mode="json"),
                "acquired",
            ):
                raise OwnershipConflict(
                    "Map startup lost original resource declaration"
                )
        if acquired.get("details") != {
            "ready": ready.model_dump(mode="json"),
            "site_started": False,
        }:
            raise OwnershipConflict("Map startup lost original ready worker")
        started_op = OperationContext.model_validate_json(
            json.dumps(start.get("operation"))
        )
        acquired_op = OperationContext.model_validate_json(
            json.dumps(acquired.get("operation"))
        )
        site.check_operation(started_op, "execute")
        site.check_operation(acquired_op, "execute")
        if (
            started_op.operation_id == acquired_op.operation_id
            or started_op.parent_operation_id is None
            or started_op.parent_operation_id != acquired_op.parent_operation_id
        ):
            raise OwnershipConflict("Map startup changed original acquisition parent")
        return service

    def _environment(
        self, selection: EnvironmentSelection, control: OperationControl
    ) -> MapEnvironmentFacts:
        selection = EnvironmentSelection.model_validate(selection)
        spec = self.read(
            selection.spec_ref, "initial-state-spec/1", InitialStateSpec, control
        )
        site = self.read(
            selection.site_spec_ref, "site-resource-spec/1", SiteResourceSpec, control
        )
        started = self.read(
            selection.site_started_ref,
            "site-resource-started/1",
            SiteResourceStarted,
            control,
        )
        configured = self.site.configuration.map_inputs
        assert configured is not None
        native_pin = (
            configured.native_contract_sha256
            if isinstance(configured, MapNavigationWorkerInputs)
            else None
        )
        if (
            site != self.site
            or started != self.started
            or spec != map_initial_spec(selection.scope.task, native_pin)
        ):
            raise OwnershipConflict(
                "Map environment changed original configured source/start/coverage"
            )
        cfg = site.configuration
        inputs = cfg.map_inputs
        assert inputs is not None
        if selection.scope != inputs.scope:
            raise OwnershipConflict("Map environment changed original complete scope")
        service = self._startup(site, started, control)
        codec = MapTaskStateCodec(selection.scope.task)
        snapshot = self.read(
            selection.snapshot_ref, codec.snapshot_schema, codec.snapshot_type, control
        )
        request = snapshot.request
        request.check_site(cfg)
        codec.check_input(request)
        private = codec.private_type.model_validate_json(request.private_input)
        binding = self.read(request.binding_ref, "task-binding/1", TaskBinding, control)
        bound = self.read(
            binding.private_spec_ref, codec.private_schema, codec.private_type, control
        )
        if (binding.identity, binding.baseline_ref, bound) != (
            selection.scope.task,
            selection.spec_ref,
            private,
        ) or hashlib.sha256(
            request.private_input.encode()
        ).hexdigest() != inputs.private_input_sha256:
            raise OwnershipConflict(
                "Map environment changed original task/input binding"
            )
        if (
            snapshot.native.plan.token != site.token
            or snapshot.native.plan.scope != selection.scope
        ):
            raise OwnershipConflict("Map environment changed original state allocation")
        self.native(snapshot.native, request, control)
        recovery = self.read(
            site.token.recovery_ref, "recovery-plan/1", RecoveryPlan, control
        )
        if (
            recovery.owner,
            recovery.attempt_id,
            recovery.baseline_ref,
            recovery.restore_component_id,
            recovery.restore_component_version,
            recovery.state_coverage,
        ) != (
            selection.scope.owner,
            None,
            selection.spec_ref,
            "map-services",
            "1",
            spec.environment_reset_checks,
        ):
            raise OwnershipConflict("Map environment recovery coverage changed")
        return MapEnvironmentFacts(spec, site, started, snapshot, service, recovery)

    def environment(
        self,
        selection: EnvironmentSelection,
        reference: EvidenceRef,
        operation: OperationContext,
        control: OperationControl,
    ) -> EnvironmentBaseline:
        facts = self._environment(selection, control)
        # The environment fact belongs to this attempt; the reusable site token
        # is batch-scoped. Only startup resource operations use token.attempt_id.
        if (
            operation.mode,
            operation.run_id,
            operation.owner_id,
            operation.attempt_id,
            operation.allocation_id,
            operation.recovery_ref,
        ) != (
            "execute",
            selection.scope.owner.run_id,
            selection.scope.owner.owner_id,
            selection.scope.attempt_id,
            facts.site.token.allocation_id,
            facts.site.token.recovery_ref,
        ):
            raise OwnershipConflict(
                "Map environment changed original attempt/allocation/recovery"
            )
        return EnvironmentBaseline(
            scope=selection.scope,
            operation=operation,
            allocation=facts.site.token,
            spec_ref=selection.spec_ref,
            measured_state_sha256=facts.snapshot.native.state_sha256,
            checks=self.checks(
                facts.spec.environment_checks,
                (
                    reference,
                    selection.site_spec_ref,
                    selection.site_started_ref,
                    selection.snapshot_ref,
                ),
                "ORIGINAL_MAP_ENVIRONMENT",
            ),
        )
