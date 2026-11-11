"""Fixed dispatch and original worker startup boundaries without actual services."""

from pathlib import Path
from typing import cast
import pytest
from lab_generate_skill.domain.native_private_json import REDDIT_PRIVATE_JSON
from lab_generate_skill.bootstrap.site_instance import build_site_instance
from lab_generate_skill.bootstrap.worker_private_artifacts import WorkerPrivateArtifacts
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.errors import InvalidTransition, OperationStopped
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.site_evidence import SitePrivateArtifacts
from lab_generate_skill.ports.native_input_commands import NativeInputCommands
from lab_generate_skill.adapters.sites.reddit_read_inputs import NativeReadInputs
from lab_generate_skill.sites.reddit.worker_instance import RedditWorkerInstance
from reddit_instance_fixtures import case as instance_case
from reddit_services_fixtures import spec
from gitlab_site_storage_live import missing_asset_configuration
from storage_installation_fixtures import storage_installation
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def config(root: Path, parent: Path) -> SiteWorkerConfiguration:
    old = missing_asset_configuration(
        storage_installation(), job_id="4752096", root=root, parent=parent
    )
    files = spec(Path(old.files.node_root)).files.model_copy(
        update={
            "workspace_root": str(root),
            "source_path": str(root / "reddit.sif"),
            "instance_id": old.token.expected_resource_id,
        }
    )
    assert old.private_evidence is not None
    return SiteWorkerConfiguration.model_validate(
        {
            **old.model_dump(),
            "site_id": "reddit",
            "files": files,
            "private_evidence": old.private_evidence.model_copy(
                update={"profile": REDDIT_PRIVATE_JSON}
            ),
        }
    )


class NoObservation:
    def observe(self, control: OperationControl) -> ProcessOwnerGuard:
        raise AssertionError("Factory must not observe or acquire anything")


def test_explicit_reddit_dispatch_requires_guard_and_has_no_effects(
    tmp_path: Path, node_path: Path
) -> None:
    configured = config(tmp_path, node_path)
    with pytest.raises(ValueError, match="original live worker guard"):
        build_site_instance(configured)
    result = build_site_instance(configured, worker_guard=NoObservation())
    assert isinstance(result, RedditWorkerInstance)
    assert isinstance(result.artifacts, WorkerPrivateArtifacts)
    assert result.instance.state == "new" and result.tasks is None
    assert not Path(configured.files.node_root).exists()
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("cancelled", [False, True])
def test_uncertain_storage_start_never_stages_native_or_retries(
    tmp_path: Path, node_path: Path, cancelled: bool
) -> None:
    configured = config(tmp_path, node_path)
    site, _, _, _ = instance_case(node_path)
    site.files_plan = configured.files
    original = (
        OperationStopped("CANCELLED", "storage")
        if cancelled
        else OSError("unknown storage create")
    )

    class Artifacts:
        calls = 0
        stopped = False

        def initialize(self, control: OperationControl) -> None:
            self.calls += 1
            raise original

        def stop_new_io(self) -> None:
            self.stopped = True

    artifacts = Artifacts()
    worker = RedditWorkerInstance(
        configured,
        site,
        cast(SitePrivateArtifacts, artifacts),
        cast(NativeInputCommands, None),
        NativeReadInputs(configured.files.node_root + "/native-input"),
        lambda control: "unused",
    )
    with pytest.raises(type(original)) as caught:
        worker.start(guard())
    assert caught.value is original and site.state == "new" and not site.generations
    assert not Path(configured.files.node_root).exists()
    with pytest.raises(InvalidTransition):
        worker.start(guard())
    assert artifacts.calls == 1
    assert worker.stop(guard()) == () and artifacts.stopped
    with pytest.raises(InvalidTransition):
        worker.start(guard())


def test_worker_task_capture_resume_use_original_instance_and_native_reader(
    tmp_path: Path, node_path: Path
) -> None:
    from datetime import datetime, timezone, timedelta
    import json
    from lab_generate_skill.domain.lifecycle import OperationContext
    from lab_generate_skill.domain.site_task import SiteTaskRequest
    from lab_generate_skill.domain.site_capture import SiteCaptureRequest
    from lab_generate_skill.domain.site_resume import SiteResumeRequest
    from lab_generate_skill.domain.site_worker import SiteInstanceStarted
    from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceContext
    from lab_generate_skill.domain.errors import OwnershipConflict
    from lab_generate_skill.adapters.processes.worker_identity import (
        current_process_identity,
    )
    from lab_generate_skill.sites.reddit.tasks.image_recovery import ImageResumed
    from reddit_image_lifecycle_fixtures import Artifacts
    from reddit_native_reader_fixtures import Commands, private_spec
    from reddit_image_state_fixtures import reference_data
    from generator_worker_fixtures import unit_guard
    from test_gitlab_ssh_key_inputs import reference

    configured = config(tmp_path, node_path)
    site, _, _, _ = instance_case(node_path)
    site.files_plan = configured.files
    context = SitePrivateEvidenceContext(
        configuration_sha256="a" * 64,
        site_id="reddit",
        token=configured.token,
        instance=SiteInstanceStarted(
            files=configured.files,
            endpoint="http://127.0.0.1:12001/",
            ports=(12001, 12002),
        ),
        owner_guard=unit_guard(current_process_identity(), guard()),
    )
    artifacts = Artifacts(tmp_path / "private-cas", context)
    commands = Commands()
    inputs = NativeReadInputs(configured.files.node_root + "/native-input")
    worker = RedditWorkerInstance(
        configured, site, artifacts, commands, inputs, lambda control: "native-user"
    )
    selected = private_spec()
    original = SiteTaskRequest(
        task=selected.task,
        binding_ref=reference(b"{}", content_schema="task-binding/1"),
        operation=OperationContext(
            operation_id="worker-snapshot",
            run_id=configured.token.owner.run_id,
            owner_id=configured.token.owner.owner_id,
            attempt_id="attempt",
            allocation_id=configured.token.allocation_id,
            recovery_ref=reference(b"{}", content_schema="recovery-plan/1"),
            deadline=datetime.now(timezone.utc) + timedelta(seconds=120),
        ),
        action="snapshot",
        private_input=selected.model_dump_json(),
    )
    with pytest.raises(InvalidTransition):
        worker.execute_task(original, control=guard())
    started = worker.start(guard())
    assert started == context.instance and worker.tasks is not None
    assert worker.tasks.reader.inputs is inputs
    saved = worker.execute_task(original, control=guard())
    assert worker.tasks.snapshot is not None
    snapref = reference(
        saved.private_result.encode(),
        content_schema=worker.tasks.snapshot.schema_version,
    )
    data = reference_data()["capture"]
    del data[
        "native_media"
    ]  # real media reader inspects the fake instance's empty tree
    commands.reply = json.dumps(
        dict(
            schema_version="reddit-native-database-capture/1",
            task=selected.task.model_dump(mode="json"),
            mode="capture",
            reference=None,
            capture=data,
        )
    ).encode()

    def next_request(action: str, name: str) -> SiteTaskRequest:
        return SiteTaskRequest.model_validate(
            {
                **original.model_dump(),
                "action": action,
                "snapshot_ref": snapref,
                "operation": original.operation.model_copy(
                    update={
                        "operation_id": name,
                        "mode": "cleanup" if action == "restore" else "execute",
                        "parent_operation_id": (
                            "worker-prepare" if action == "restore" else None
                        ),
                    }
                ),
            }
        )

    with pytest.raises(OwnershipConflict):
        worker.execute_task(
            original.model_copy(
                update={
                    "operation": original.operation.model_copy(
                        update={"allocation_id": "foreign"}
                    )
                }
            ),
            control=guard(),
        )
    worker.execute_task(next_request("prepare", "worker-prepare"), control=guard())
    capture = SiteCaptureRequest(
        inspection=next_request("inspect", "worker-capture"),
        collector_id="reddit-native-image",
        collector_version="1",
    )
    assert (
        worker.capture_task(capture, control=guard()).request_sha256 == capture.digest
    )
    restore = next_request("restore", "worker-restore")
    restored = worker.execute_task(restore, control=guard())
    resume = SiteResumeRequest(
        restore_request=restore,
        restore_result_ref=reference(
            restored.model_dump_json().encode(), content_schema="site-task-result/1"
        ),
        operation=restore.operation.cleanup(
            "worker-resume", now=datetime.now(timezone.utc), seconds=20
        ).model_copy(update={"recovery_ref": configured.token.recovery_ref}),
    )
    resumed = worker.resume_frontend(resume, control=guard())
    assert ImageResumed.model_validate_json(resumed.private_result).request == resume
    assert len(commands.calls) == 4  # reference, prepare, capture, post-resume
    assert len(site.generations) == 3
    worker.stop(guard())
    with pytest.raises(InvalidTransition):
        worker.capture_task(capture, control=guard())
    with pytest.raises(InvalidTransition):
        worker.resume_frontend(resume, control=guard())
    assert len(commands.calls) == 4
