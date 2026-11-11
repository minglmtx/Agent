"""Actual lifecycle/immutable ID file/CAS with explicitly synthetic native effects."""

from dataclasses import dataclass
import hashlib
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
from lab_generate_skill.adapters.sites.reddit_read_inputs import NativeReadInputs
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.reddit_native_read_input import BaselineIdsRef
from lab_generate_skill.domain.site_private_fact import (
    SitePrivateEvidenceContext,
    SitePrivateEvidenceResult,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_worker import SiteInstanceStarted
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.reddit.native_reader import RedditNativeReader
from lab_generate_skill.sites.reddit.native_schema import NativeCapture
from lab_generate_skill.sites.reddit.image_state import ImageReference
from lab_generate_skill.sites.reddit.tasks.image_spec import NativeImageSpec
from lab_generate_skill.sites.reddit.tasks.image_lifecycle import ImageLifecycle
from gitlab_ssh_lifecycle_fixtures import Artifacts as BaseArtifacts
from reddit_instance_fixtures import case as instance_case
from reddit_native_reader_fixtures import private_spec
from reddit_image_state_fixtures import reference_data
from generator_worker_fixtures import unit_guard
from site_worker_fixtures import configuration
from test_gitlab_ssh_key_inputs import reference
from test_slurm_commands import guard


class Reader(RedditNativeReader):
    def __init__(self, inputs: NativeReadInputs) -> None:
        self.inputs = inputs
        initial = reference_data()
        initial["capture"]["native_media"]["directories"] = ["submission_images"]
        self.initial = ImageReference.model_validate_json(json.dumps(initial))
        self.value = self.initial.capture
        self.last_database = None
        self.last_result = None
        self.calls = 0
        self.error: BaseException | None = None

    def reference(
        self, spec: NativeImageSpec, username: str, control: OperationControl
    ) -> ImageReference:
        control.checkpoint()
        self.calls += 1
        assert username == self.initial.account.username
        if self.error is not None:
            raise self.error
        self.last_result = self.initial
        return self.initial

    def capture(
        self,
        spec: NativeImageSpec,
        username: str,
        baseline: BaselineIdsRef,
        control: OperationControl,
    ) -> NativeCapture:
        control.checkpoint()
        self.calls += 1
        assert spec.task == baseline.task and username == self.initial.account.username
        self.inputs.verify(baseline, control)
        if self.error is not None:
            raise self.error
        self.last_result = self.value
        return self.value


class Artifacts(BaseArtifacts):
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
                content_schema="reddit-native-private-json/1",
                visibility="private",
                producer="fixed-reddit-native-private-v1",
            ),
            control,
        )
        return SitePrivateEvidenceResult(
            request_sha256=request.digest, context=self.context, payload_ref=ref
        )


@dataclass
class Case:
    task: ImageLifecycle
    reader: Reader
    artifacts: Artifacts
    request: SiteTaskRequest

    def next(
        self, action: str, name: str, *, snapshot_ref: EvidenceRef | None = None
    ) -> SiteTaskRequest:
        assert self.task.snapshot is not None
        parent = self.task.preparation or self.task.snapshot.request
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
                "operation": operation,
                "snapshot_ref": snapshot_ref
                or self.task.snapshot_ref
                or reference(
                    self.task.snapshot.model_dump_json().encode(),
                    content_schema=self.task.snapshot.schema_version,
                ),
            }
        )


def case(
    root: Path,
    *,
    configured: SiteWorkerConfiguration | None = None,
    owner_guard: ProcessOwnerGuard | None = None,
) -> Case:
    site, _, _, _ = instance_case(root)
    if configured is not None:
        site.files_plan = configured.files
    spec = site.prepare(guard())
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
        site_id="reddit",
        token=token,
        instance=SiteInstanceStarted(
            files=site.files_plan, endpoint=endpoint, ports=site.lease.ports
        ),
        owner_guard=owner_guard or unit_guard(current_process_identity(), guard()),
    )
    artifacts = Artifacts(root / "private-evidence", context)
    reader = Reader(NativeReadInputs(spec.native_input_root))
    selected = private_spec()
    request = SiteTaskRequest(
        task=selected.task,
        binding_ref=reference(b"{}", content_schema="task-binding/1"),
        operation=OperationContext(
            operation_id="image-snapshot",
            run_id=token.owner.run_id,
            owner_id=token.owner.owner_id,
            attempt_id="attempt",
            allocation_id=token.allocation_id,
            recovery_ref=reference(b"{}", content_schema="recovery-plan/1"),
            deadline=datetime.now(timezone.utc) + timedelta(seconds=120),
        ),
        action="snapshot",
        private_input=selected.model_dump_json(),
    )
    return Case(
        ImageLifecycle(site, reader, lambda control: "native-user", artifacts),
        reader,
        artifacts,
        request,
    )
