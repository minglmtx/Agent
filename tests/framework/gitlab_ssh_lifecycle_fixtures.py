"""Real native lifecycle/CAS primitives with explicit simulated SQL/services."""

from dataclasses import dataclass
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_worker import (
    SiteInstanceStarted,
    SiteWorkerConfiguration,
)
from lab_generate_skill.domain.site_private_fact import (
    SitePrivateEvidenceContext,
    SitePrivateEvidenceResult,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.native_private_json import (
    GITLAB_PRIVATE_JSON,
    NativePrivateJsonProfile,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.gitlab.ssh_native_reader import GitlabSshNativeReader
from lab_generate_skill.sites.gitlab.tasks.ssh_key_spec import SshKeySpec
from lab_generate_skill.sites.gitlab.tasks.ssh_key_state import SshKeyNativeState
from lab_generate_skill.sites.gitlab.tasks.ssh_key_lifecycle import SshKeyLifecycle
from lab_generate_skill.sites.gitlab.tasks.ssh_key_recovery import (
    SshKeyRecoverySnapshot,
)
from evidence_control_fixtures import EvidenceFixtureStore
from gitlab_ssh_state_fixtures import native_state, selected_spec
from test_gitlab_instance import instance
from site_worker_fixtures import configuration
from generator_worker_fixtures import unit_guard
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from test_gitlab_ssh_key_inputs import reference
from test_slurm_commands import guard


class Reader(GitlabSshNativeReader):
    def __init__(self) -> None:
        self.value = native_state()
        self.captured_raw = None
        self.calls = 0
        self.error: BaseException | None = None

    def capture(
        self, spec: SshKeySpec, username: str, control: OperationControl
    ) -> SshKeyNativeState:
        control.checkpoint()
        self.calls += 1
        self.captured_raw = None
        assert spec.task == self.value.task and username == self.value.account.username
        if self.error is not None:
            raise self.error
        self.captured_raw = self.value.model_dump_json().encode()
        return self.value


class Artifacts:
    def __init__(
        self,
        root: Path,
        context: SitePrivateEvidenceContext,
        *,
        profile: NativePrivateJsonProfile = GITLAB_PRIVATE_JSON,
    ) -> None:
        root.mkdir(mode=0o700)
        self.store = EvidenceFixtureStore(root)
        self.context = context
        self.profile = profile
        self.calls: list[str] = []
        self.error: BaseException | None = None

    def initialize(self, control: OperationControl) -> None:
        control.checkpoint()

    def bind_instance(
        self, started: SiteInstanceStarted, control: OperationControl
    ) -> None:
        control.checkpoint()

    def stop_new_io(self) -> None:
        pass

    def publish(
        self, request: SiteTaskRequest, raw: bytes, *, control: OperationControl
    ) -> SitePrivateEvidenceResult:
        self.calls.append(request.operation.operation_id)
        if self.error is not None:
            raise self.error
        ref = self.store.put(
            raw,
            EvidenceMetadata(
                media_type="application/json",
                content_schema=self.profile.content_schema,
                visibility="private",
                producer=self.profile.producer,
            ),
            control,
        )
        return SitePrivateEvidenceResult(
            request_sha256=request.digest, context=self.context, payload_ref=ref
        )

    def read(
        self,
        request: SiteTaskRequest,
        result: SitePrivateEvidenceResult,
        *,
        control: OperationControl,
    ) -> bytes:
        assert result.request_sha256 == request.digest
        return self.store.read(result.payload_ref, control)


@dataclass
class Case:
    task: SshKeyLifecycle
    reader: Reader
    artifacts: Artifacts
    request: SiteTaskRequest

    def next(
        self, action: str, name: str, *, snapshot_ref: EvidenceRef | None = None
    ) -> SiteTaskRequest:
        task = self.task
        assert task.snapshot is not None
        parent = task.preparation or task.snapshot.request
        operation = self.request.operation.model_copy(
            update={
                "operation_id": name,
                "mode": "cleanup" if action == "restore" else "execute",
                "parent_operation_id": (
                    parent.operation.operation_id if action == "restore" else None
                ),
            }
        )
        return SiteTaskRequest.model_validate(
            {
                **self.request.model_dump(),
                "action": action,
                "snapshot_ref": snapshot_ref
                or task.snapshot_ref
                or reference(
                    task.snapshot.model_dump_json().encode(),
                    content_schema=task.snapshot.schema_version,
                ),
                "operation": operation,
            }
        )


def case(
    root: Path,
    *,
    configured: SiteWorkerConfiguration | None = None,
    owner_guard: ProcessOwnerGuard | None = None,
    native_shutdown: bool = False,
) -> Case:
    site, _, _, _ = instance(root, native_shutdown=native_shutdown)
    if configured is not None:
        site.files_plan = configured.files
    site.prepare(guard())
    endpoint = site.start(guard())
    base = configuration() if configured is None else configured
    token = base.token.model_copy(
        update={"expected_resource_id": site.files_plan.instance_id}
    )
    assert site.lease is not None
    context = SitePrivateEvidenceContext(
        configuration_sha256=(
            "a" * 64
            if configured is None
            else hashlib.sha256(configured.model_dump_json().encode()).hexdigest()
        ),
        token=token,
        instance=SiteInstanceStarted(
            files=site.files_plan, endpoint=endpoint, ports=site.lease.ports
        ),
        owner_guard=owner_guard or unit_guard(current_process_identity(), guard()),
    )
    artifacts = Artifacts(root / "private-evidence", context)
    reader = Reader()
    request = SiteTaskRequest(
        task=selected_spec().task,
        binding_ref=reference(b"{}", content_schema="task-binding/1"),
        operation=OperationContext(
            operation_id="ssh-snapshot",
            run_id=token.owner.run_id,
            owner_id=token.owner.owner_id,
            attempt_id="attempt",
            allocation_id=token.allocation_id,
            recovery_ref=reference(b"{}", content_schema="recovery-plan/1"),
            deadline=datetime.now(timezone.utc) + timedelta(seconds=120),
        ),
        action="snapshot",
        private_input=selected_spec().model_dump_json(),
    )
    return Case(
        SshKeyLifecycle(site, reader, lambda control: "native-user", artifacts),
        reader,
        artifacts,
        request,
    )
