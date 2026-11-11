"""Live capability gates, with explicit simulated kernel observations only."""

import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Literal, cast
import pytest
from lab_generate_skill.domain.native_private_json import (
    GITLAB_PRIVATE_JSON,
    GITLAB_GROUP_PRIVATE_JSON,
    REDDIT_PRIVATE_JSON,
    NativePrivateJsonProfile,
)
from lab_generate_skill.adapters.sites.storage_admission import (
    OriginalSiteStorageAdmission,
)
import lab_generate_skill.adapters.sites.storage_participant as module
from lab_generate_skill.adapters.sites.storage_original import (
    OriginalSiteAcquisitionReader,
)
from lab_generate_skill.adapters.slurm.linux_cgroups import KernelCgroupObservation
from lab_generate_skill.adapters.slurm.kernel_capture import KernelCapture
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.scheduler import SlurmExecutionIdentity
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceContext
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict, InvalidTransition
from lab_generate_skill.domain.storage_termination import StorageProcessEnd
from lab_generate_skill.ports.lifecycle import OperationControl
from site_storage_fixtures import private_configuration
from site_resource_fixtures import resource_case
from test_site_resource import enter
from gitlab_ssh_state_fixtures import selected_spec
from test_gitlab_ssh_key_inputs import reference
from test_slurm_commands import guard


class LiveGuard:
    def __init__(self, value: ProcessOwnerGuard) -> None:
        self.value = value

    def observe(self, control: OperationControl) -> ProcessOwnerGuard:
        control.checkpoint()
        return self.value


@pytest.mark.parametrize("participant", ["worker", "controller"])
@pytest.mark.parametrize(
    "change",
    ["mount_id", "device", "user_inode", "task_inode", "uid", "writer", "step", "job"],
)
def test_original_physical_cgroup_identity_across_observer_mount_views(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    participant: Literal["worker", "controller"],
    change: str,
) -> None:
    c = resource_case(tmp_path, monkeypatch, config=private_configuration(tmp_path))
    with enter(c) as registered:
        expected = registered.site.ready.worker.owner_guard
        identity = expected.worker if participant == "worker" else expected.controller
        original = (
            registered.site.ready.controller.target.worker
            if participant == "worker"
            else c.spec.slurm.parent
        )
        value = original.model_dump()
        if change == "writer":
            value["writer"] = identity.model_copy(
                update={"start_ticks": identity.start_ticks + 1}
            )
        elif change == "step":
            value.update(
                step_id="9",
                user_path=original.user_path.replace(
                    "/step_" + original.step_id + "/", "/step_9/"
                ),
            )
        elif change == "job":
            value.update(
                job_id="999999",
                user_path=original.user_path.replace(
                    "/job_" + original.job_id + "/", "/job_999999/"
                ),
            )
        else:
            value[change] += 1000
        changed = type(original).model_validate(value)
        monkeypatch.setattr(module, "current_process_identity", lambda: identity)
        monkeypatch.setattr(
            module,
            "observe_current_cgroup",
            lambda *args: KernelCgroupObservation(changed, KernelCapture((), ())),
        )
        admission = OriginalSiteStorageAdmission(
            c.spec.configuration,
            participant,
            OriginalSiteAcquisitionReader(),
            LiveGuard(expected) if participant == "worker" else None,
            None,
        )
        plan = admission.plan
        operation = op("physical-identity")
        if participant == "worker" and change == "mount_id":
            admission.authorize_storage(plan.binding, plan.config, operation, guard())
            assert admission.accepted == {operation.operation_id: operation}
        else:
            with pytest.raises(OwnershipConflict):
                admission.authorize_storage(
                    plan.binding, plan.config, operation, guard()
                )
            assert admission.accepted == {}


def op(name: str) -> OperationContext:
    return OperationContext(
        operation_id=name,
        run_id="run",
        owner_id="owner",
        deadline=datetime.now(timezone.utc) + timedelta(seconds=30),
    )


@pytest.mark.parametrize("participant", ["worker", "controller"])
@pytest.mark.parametrize(
    "site_id,profile",
    [
        ("gitlab", GITLAB_PRIVATE_JSON),
        ("gitlab", GITLAB_GROUP_PRIVATE_JSON),
        ("reddit", REDDIT_PRIVATE_JSON),
    ],
)
def test_scope_owner_exact_physical_ops_repeat_and_original_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    participant: Literal["worker", "controller"],
    site_id: Literal["gitlab", "reddit"],
    profile: NativePrivateJsonProfile,
) -> None:
    cfg = private_configuration(tmp_path)
    assert cfg.private_evidence is not None
    cfg = cfg.model_copy(
        update={
            "site_id": site_id,
            "private_evidence": cfg.private_evidence.model_copy(
                update={"profile": profile}
            ),
        }
    )
    c = resource_case(tmp_path, monkeypatch, config=cfg)
    with enter(c) as registered:
        original = OriginalSiteAcquisitionReader().read(c.spec.configuration, guard())
        expected = original.acquired.details.ready.worker.owner_guard
        identity = expected.worker if participant == "worker" else expected.controller
        member = (
            original.acquired.details.ready.controller.target.worker
            if participant == "worker"
            else c.spec.slurm.parent
        )
        monkeypatch.setattr(module, "current_process_identity", lambda: identity)

        def observe(
            execution: SlurmExecutionIdentity,
            writer: ProcessIdentity,
            control: OperationControl,
        ) -> KernelCgroupObservation:
            assert execution == c.spec.slurm.execution and writer == identity
            return KernelCgroupObservation(member, KernelCapture((), ()))

        monkeypatch.setattr(module, "observe_current_cgroup", observe)
        live = LiveGuard(expected) if participant == "worker" else None
        admission = OriginalSiteStorageAdmission(
            c.spec.configuration,
            participant,
            OriginalSiteAcquisitionReader(),
            live,
            None,
        )
        plan = admission.plan
        operation = op("physical-once")
        admission.authorize_storage(plan.binding, plan.config, operation, guard())
        with pytest.raises(InvalidTransition):
            admission.authorize_storage(plan.binding, plan.config, operation, guard())
        admission.bind_instance(registered.site.instance, guard())
        with pytest.raises(InvalidTransition):
            admission.bind_instance(registered.site.instance, guard())
        context = SitePrivateEvidenceContext(
            site_id=site_id,
            configuration_sha256=hashlib.sha256(
                c.spec.configuration.model_dump_json().encode()
            ).hexdigest(),
            token=c.spec.token,
            instance=registered.site.instance,
            owner_guard=expected,
        )
        task_identity = selected_spec().task
        if profile == GITLAB_GROUP_PRIVATE_JSON:
            from gitlab_group_fixtures import selected_spec as group_spec

            task_identity = group_spec().task
        if site_id == "reddit":
            from test_reddit_image_inputs import public_task

            task_identity = public_task().identity
        request = SiteTaskRequest(
            task=task_identity,
            binding_ref=reference(b"{}", content_schema="task-binding/1"),
            operation=c.op.model_copy(
                update={
                    "attempt_id": "native-attempt",
                    "operation_id": "native-capture",
                }
            ),
            action="inspect",
            snapshot_ref=reference(b"{}", content_schema="gitlab-full-recovery/1"),
            private_input=selected_spec().model_dump_json(),
        )
        admission.authorize(plan, context, request, "read", guard())
        with pytest.raises(OwnershipConflict):
            admission.authorize(
                plan,
                context.model_copy(
                    update={"site_id": "reddit" if site_id == "gitlab" else "gitlab"}
                ),
                request,
                "read",
                guard(),
            )
        if participant == "worker":
            admission.authorize(plan, context, request, "publish", guard())
        else:
            with pytest.raises(OwnershipConflict):
                admission.authorize(plan, context, request, "publish", guard())
        wrong = context.model_copy(
            update={
                "instance": context.instance.model_copy(
                    update={"endpoint": "http://127.0.0.1:9999/", "ports": (9999,)}
                )
            }
        )
        with pytest.raises(OwnershipConflict):
            admission.authorize(plan, wrong, request, "read", guard())
        admission.stop_new_io()
        with pytest.raises(InvalidTransition):
            admission.authorize_storage(plan.binding, plan.config, op("new"), guard())
        cleanup = operation.cleanup(
            "original-cleanup", now=datetime.now(timezone.utc), seconds=10
        )
        admission.authorize_cleanup(
            plan.binding, plan.config, operation, cleanup, None, guard()
        )
        with pytest.raises(ValueError):
            admission.authorize_cleanup(
                plan.binding, plan.config, op("never-admitted"), cleanup, None, guard()
            )
        never = op("unowned")
        unowned_cleanup = never.cleanup(
            "unowned-cleanup", now=datetime.now(timezone.utc), seconds=10
        )
        with pytest.raises(OwnershipConflict):
            admission.authorize_cleanup(
                plan.binding, plan.config, never, unowned_cleanup, None, guard()
            )
        with pytest.raises(ValueError):
            admission.authorize_cleanup(
                plan.binding,
                plan.config,
                operation,
                cleanup,
                cast(StorageProcessEnd, {}),
                guard(),
            )
        ending = StorageProcessEnd(
            controller=identity.model_copy(
                update={"start_ticks": identity.start_ticks + 1}
            ),
            request_sha256="a" * 64,
            process_id=identity.process_id + 10000,
            returncode=0,
            observed_at=datetime.now(timezone.utc),
            capture_sha256="b" * 64,
            kill_requested=False,
        )
        with pytest.raises(OwnershipConflict):
            admission.authorize_cleanup(
                plan.binding, plan.config, operation, cleanup, ending, guard()
            )


@pytest.mark.parametrize(
    "failure", ["process", "cgroup", "guard", "scope", "thread", "binding"]
)
def test_wrong_live_scope_rejects_before_private_store_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    c = resource_case(tmp_path, monkeypatch, config=private_configuration(tmp_path))
    with enter(c) as registered:
        expected = registered.site.ready.worker.owner_guard
        member = registered.site.ready.controller.target.worker
        monkeypatch.setattr(
            module,
            "current_process_identity",
            lambda: expected.worker if failure != "process" else expected.controller,
        )
        monkeypatch.setattr(
            module,
            "observe_current_cgroup",
            lambda *args: KernelCgroupObservation(
                member if failure != "cgroup" else c.spec.slurm.parent,
                KernelCapture((), ()),
            ),
        )
        live = LiveGuard(
            expected
            if failure != "guard"
            else expected.model_copy(update={"parent_death_signal": "wrong"})
        )
        admission = OriginalSiteStorageAdmission(
            c.spec.configuration, "worker", OriginalSiteAcquisitionReader(), live, None
        )
        if failure == "thread":
            admission.owner = (0, 0)
        operation = op("rejected")
        if failure == "scope":
            operation = operation.model_copy(
                update={"attempt_id": "not-physical-scope"}
            )
        plan = admission.plan
        binding = (
            plan.binding
            if failure != "binding"
            else plan.binding.model_copy(update={"session_id": "foreign"})
        )
        with pytest.raises(OwnershipConflict):
            admission.authorize_storage(binding, plan.config, operation, guard())
        assert admission.accepted == {}
