"""Real dispatch/wire/journal/CAS/files; explicit synthetic native/kernel effects."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
import pytest
import lab_generate_skill.bootstrap.map_instance as assembly
import lab_generate_skill.adapters.sites.storage_participant as participant
from lab_generate_skill.bootstrap.site_instance import build_site_instance
from lab_generate_skill.bootstrap.map_task_configuration import map_task_configuration
from lab_generate_skill.adapters.sites.worker_service import SiteService
from lab_generate_skill.adapters.sites.storage_original import (
    OriginalSiteAcquisitionReader,
)
from lab_generate_skill.adapters.slurm.linux_cgroups import KernelCgroupObservation
from lab_generate_skill.adapters.slurm.kernel_capture import KernelCapture
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.map_origin import MapOriginPolicy
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from lab_generate_skill.sites.map.tasks.navigation_spec import NavigationSpec
from map_navigation_fixtures import navigation_case
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_quiescence import QuiescentNativeServices
from lab_generate_skill.sites.map.worker_instance import MapWorkerInstance
from lab_generate_skill.sites.map.instance import MapInstance
from lab_generate_skill.sites.map.tasks.overlay_spec import NativeOverlaySpec
from map_instance_fixtures import InstanceCase
from map_service_generations_fixtures import GenerationCase, OneGroup
from map_state_fixtures import SQL
from site_worker_fixtures import configuration, sources
from site_resource_fixtures import resource_case, ResourceChannel
from generator_worker_fixtures import unit_guard
from test_site_storage_admission import LiveGuard
from test_core_contracts import reference
from test_slurm_commands import guard


class NativeGroup(OneGroup):
    def start(
        self, name: str, argv: tuple[str, ...], control: OperationControl
    ) -> None:
        super().start(name, argv, control)
        if name == "rails_server":
            # Explicit simulated first Rails asset compilation, before guard.
            root = Path(self.spec.inputs.node_tree("frontend"))
            public = root / "public"
            if not public.exists():
                public.mkdir(mode=0o700)
                (public / "compiled.js").write_bytes(b"synthetic compiled asset")


class NativeGeneration(GenerationCase):
    def factory(self, path: Path) -> QuiescentNativeServices:
        assert path.is_dir() and not list(path.iterdir())
        group = NativeGroup(self.case, len(self.groups))
        self.groups.append(group)
        return group


class RegisteredMapCase:
    def __init__(
        self,
        root: Path,
        patch: pytest.MonkeyPatch,
        *,
        navigation_source: str | None = None,
        task_scope: StateScope | None = None,
        origin: MapOriginPolicy | None = None,
    ) -> None:
        self.case = InstanceCase(root, patch)
        self.generation = NativeGeneration(self.case)
        self.workspace = Path(self.case.spec.inputs.files.workspace_root)
        self.workspace.chmod(0o700)
        base = configuration(job_id="4752096")
        task = TaskIdentity(
            site="map",
            family="native_route_map_data",
            contract_version=1,
            split="train",
            task_id="b9101b71aacd51b61f6e",
            source_task_id="b9101b71aacd51b61f6e",
        )
        self.private: NativeOverlaySpec | NavigationSpec = NativeOverlaySpec(
            task=task, native_contract_ref=reference("private", "map-native-contract/1")
        )
        if navigation_source is not None:
            self.private = navigation_case(navigation_source).load().private_spec
            task = self.private.task
        self.scope = task_scope or StateScope(
            owner=base.token.owner,
            task=task,
            attempt_id="attempt",
            context_id="context",
        )
        cfg = map_task_configuration(
            self.case.spec.inputs,
            self.private,
            self.scope,
            base.token.model_copy(
                update={"expected_resource_id": self.case.spec.inputs.files.instance_id}
            ),
            base.installation,
            origin=(
                (MapOriginPolicy.dynamic() if origin is None else origin)
                if isinstance(self.private, NavigationSpec)
                else origin
            ),
            evidence_root=self.workspace / "evidence",
            resource_journal_root=self.workspace / "journal",
            artifact_root=self.workspace / "map-files",
            max_files=100,
            max_file_bytes=256 * 1024**2,
            max_total_bytes=512 * 1024**2,
        )
        self.resource = resource_case(self.workspace, patch, config=cfg)
        self.configuration = self.resource.spec.configuration
        expected_port = (
            cfg.map_inputs.origin.requested_web_port
            if isinstance(cfg.map_inputs, MapNavigationWorkerInputs)
            else None
        )
        if expected_port is not None:
            self.generation.instance = self.case.build(
                services=self.generation.services, expected_web_port=expected_port
            )
        self.owner_guard = unit_guard(self.resource.spec.slurm.parent.writer, guard())
        self.live = LiveGuard(self.owner_guard)
        self.observer: Literal["worker", "controller"] = "worker"
        self.member_change: dict[str, Any] = {}
        self.reader = OriginalSiteAcquisitionReader()
        self.worker: MapWorkerInstance | None = None
        self.sql = SQL()
        self.snapshot_ref: EvidenceRef | None = None
        self.binding = self.put(
            b'{"fixture":"original task binding"}', "task-binding/1"
        )
        self.task_recovery = self.put(
            b'{"fixture":"original task recovery"}', "recovery-plan/1"
        )

        def identity() -> Any:
            return (
                self.owner_guard.worker
                if self.observer == "worker"
                else self.owner_guard.controller
            )

        def kernel(*args: Any) -> KernelCgroupObservation:
            original = self.reader.read(self.configuration, guard())
            expected = (
                original.acquired.details.ready.controller.target.worker
                if self.observer == "worker"
                else original.spec.slurm.parent
            )
            changed = type(expected).model_validate(
                {**expected.model_dump(), **self.member_change}
            )
            return KernelCgroupObservation(changed, KernelCapture((), ()))

        def instance(*args: Any, **kwargs: Any) -> MapInstance:
            assert args[0] == self.case.spec.inputs
            assert (
                kwargs["expected_web_port"]
                == self.generation.instance.expected_web_port
            )
            return self.generation.instance

        def factory(value: SiteWorkerConfiguration) -> MapWorkerInstance:
            result = build_site_instance(value, worker_guard=self.live)
            assert isinstance(result, MapWorkerInstance)
            self.worker = result
            return result

        def channel(*args: Any, **kwargs: Any) -> ResourceChannel:
            result = ResourceChannel(self.resource)
            result.service = SiteService(factory, sources, unit_guard)
            self.resource.channels.append(result)
            return result

        patch.setattr(participant, "current_process_identity", identity)
        patch.setattr(
            "lab_generate_skill.adapters.map_artifacts.site_storage.current_process_identity",
            identity,
        )
        patch.setattr(participant, "observe_current_cgroup", kernel)
        patch.setattr(assembly, "MapInstance", instance)
        patch.setattr(
            assembly, "CheckedNativeCommands", lambda runner: self.case.commands
        )
        patch.setattr(assembly, "CheckedNativeInputCommands", lambda runner: self.sql)
        patch.setattr(
            "lab_generate_skill.adapters.sites.resource.FramedProcessSession", channel
        )

    def put(self, raw: bytes, schema: str) -> EvidenceRef:
        return self.resource.evidence.put(
            raw,
            EvidenceMetadata(
                media_type="application/json",
                content_schema=schema,
                visibility="private",
                producer="fixture-map-control",
            ),
            control=guard(),
        )

    def request(self, action: str, label: str | None = None) -> SiteTaskRequest:
        parent = None
        if action == "restore":
            assert (
                self.worker is not None
                and self.worker.tasks is not None
                and self.worker.tasks.snapshot is not None
            )
            parent = (
                self.worker.tasks.preparation or self.worker.tasks.snapshot.request
            ).operation.operation_id
        op = OperationContext(
            operation_id=label or action,
            run_id=self.scope.owner.run_id,
            owner_id=self.scope.owner.owner_id,
            attempt_id=self.scope.attempt_id,
            allocation_id=self.configuration.token.allocation_id,
            recovery_ref=self.task_recovery,
            mode="cleanup" if action == "restore" else "execute",
            parent_operation_id=parent,
            deadline=datetime.now(timezone.utc) + timedelta(seconds=120),
        )
        return SiteTaskRequest.model_validate(
            dict(
                task=self.scope.task,
                binding_ref=self.binding,
                operation=op,
                action=action,
                snapshot_ref=None if action == "snapshot" else self.snapshot_ref,
                private_input=self.private.model_dump_json(),
            )
        )

    def resume_request(self, restored: SiteTaskResult) -> SiteResumeRequest:
        assert self.worker is not None and self.worker.tasks is not None
        old = self.worker.tasks.restore_request
        assert old is not None
        op = OperationContext.model_validate(
            {
                **old.operation.model_dump(),
                "operation_id": "resume",
                "parent_operation_id": old.operation.operation_id,
                "recovery_ref": self.configuration.token.recovery_ref,
            }
        )
        return SiteResumeRequest(
            restore_request=old,
            restore_result_ref=self.put(
                restored.model_dump_json().encode(), "site-task-result/1"
            ),
            operation=op,
        )

    def close_sockets(self) -> None:
        self.generation.close_sockets()
