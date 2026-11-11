"""Synthetic site worker dependencies; never production launch permission."""

from datetime import datetime, timedelta, timezone
from typing import Literal
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.release_installation import (
    ReleaseInstallation,
    InstalledReleaseSources,
    InstalledReleaseModule,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import (
    ResourceOwner,
    AllocationToken,
    OperationContext,
)
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.sites.worker_protocol import (
    WORKER_MODULE,
    decode_command,
    Phase,
)
from lab_generate_skill.adapters.sites.worker_service import SiteService
from lab_generate_skill.adapters.sites.worker_client import SupervisedSiteInstance
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    ProcessTermination,
)
from generator_worker_fixtures import unit_guard
from storage_installation_fixtures import storage_installation, unit_storage_sources


def configuration(
    installation: ReleaseInstallation | None = None, *, job_id: str = "job"
) -> SiteWorkerConfiguration:
    files = SiteFilesPlan(
        instance_id="site-instance",
        workspace_root="/anvme/workspace/site-unit",
        source_path="/anvme/workspace/site-unit/admin.sif",
        node_root="/tmp/site-worker-unit",
        image=ReleaseFile(
            path="admin.sif", size_bytes=1, sha256="0" * 64, executable=False
        ),
    )
    ref = EvidenceRef(
        uri="cas:unit-recovery",
        sha256="0" * 64,
        size_bytes=0,
        media_type="application/json",
        content_schema="recovery-plan/1",
        visibility="private",
        producer="unit",
    )
    token = AllocationToken(
        allocation_id="site-allocation",
        owner=ResourceOwner(
            run_id="run", owner_id="owner", job_id=job_id, worker_id="worker"
        ),
        scope="batch",
        resource_kind="site",
        expected_resource_id=files.instance_id,
        provider_id="fixed-site-worker",
        provider_version="6",
        recovery_ref=ref,
    )
    return SiteWorkerConfiguration(
        site_id="shopping_admin",
        token=token,
        files=files,
        apptainer="/usr/bin/apptainer",
        installation=installation or storage_installation(),
        private_evidence=None,
    )


def operation(config: SiteWorkerConfiguration) -> OperationContext:
    token = config.token
    return OperationContext(
        operation_id="site-start",
        run_id=token.owner.run_id,
        owner_id=token.owner.owner_id,
        allocation_id=token.allocation_id,
        recovery_ref=token.recovery_ref,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=240),
    )


def sources(
    installation: ReleaseInstallation, control: OperationControl
) -> InstalledReleaseSources:
    control.checkpoint()
    value = unit_storage_sources(installation)
    module = InstalledReleaseModule(
        name=WORKER_MODULE, filename=value.package_root + "/bootstrap/site_worker.py"
    )
    return value.model_copy(
        update={
            "modules": tuple(sorted((*value.modules, module), key=lambda x: x.name))
        }
    )


class Authority:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.error: BaseException | None = None

    def verify(
        self,
        config: SiteWorkerConfiguration,
        phase: Literal["configure", "start", "close"],
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.calls.append(phase)
        if self.error:
            raise self.error

    def verify_task(
        self,
        config: SiteWorkerConfiguration,
        request: SiteTaskRequest,
        control: OperationControl,
    ) -> None:
        request.check_site(config)
        control.checkpoint()
        self.calls.append("task")
        if self.error:
            raise self.error


class Instance:
    def __init__(self, config: SiteWorkerConfiguration) -> None:
        self.config = config
        self.calls: list[str] = []
        self.error: BaseException | None = None
        self.cleanup_error: BaseException | None = None
        self.unconfirmed = False

    def start(self, control: OperationControl) -> SiteInstanceStarted:
        control.checkpoint()
        self.calls.append("start")
        if self.error:
            raise self.error
        return SiteInstanceStarted(
            files=self.config.files,
            endpoint=(
                "http://127.0.0.1:12001/"
                if self.config.site_id == "shopping"
                else "http://127.0.0.1:12001/admin"
            ),
            ports=(12001, 12002, 12003, 12004, 12005),
        )

    def execute_task(
        self, request: SiteTaskRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        control.checkpoint()
        self.calls.append("task")
        if self.error:
            raise self.error
        return SiteTaskResult(
            request_sha256=request.digest, private_result='{"unit":true}'
        )

    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
        control.checkpoint()
        self.calls.append("stop")
        if self.cleanup_error:
            raise self.cleanup_error
        return (
            NativeServiceExit(
                service="unit",
                process_id=1,
                returncode=None if self.unconfirmed else 0,
                state="unconfirmed" if self.unconfirmed else "reaped",
                kill_requested=False,
            ),
        )


class Channel:
    def __init__(self, service: SiteService) -> None:
        self.service = service
        self.calls: list[bytes] = []
        self.aborts = 0
        self.finishes = 0
        self.capture = CommandCapture(("/unit-worker",), None, b"", b"", False)
        self.error: BaseException | None = None
        self.bad_reply: bytes | None = None
        self.abort_error: BaseException | None = None

    def exchange(self, payload: bytes, control: OperationControl) -> bytes:
        control.checkpoint()
        self.calls.append(payload)
        if self.error:
            raise self.error
        raw = self.service.handle(decode_command(payload)).model_dump_json().encode()
        return raw if self.bad_reply is None else self.bad_reply

    def abort(self, control: OperationControl) -> ProcessTermination:
        self.aborts += 1
        self.service.close()
        if self.abort_error:
            raise self.abort_error
        return ProcessTermination(1, "reaped", -9, True)

    def finish(self, control: OperationControl) -> ProcessTermination:
        self.finishes += 1
        assert self.service.closed
        return ProcessTermination(1, "reaped", 0, False)


def case() -> tuple[Instance, SiteService, Channel, SupervisedSiteInstance, Authority]:
    config = configuration()
    instance = Instance(config)
    service = SiteService(lambda c: instance, sources, unit_guard)
    channel = Channel(service)
    authority = Authority()
    return (
        instance,
        service,
        channel,
        SupervisedSiteInstance(channel, "site-session", config, authority),
        authority,
    )
