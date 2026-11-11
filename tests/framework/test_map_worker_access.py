"""Frozen Map configuration and actual acquired-resource file capability checks."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.errors import OwnershipConflict, InvalidTransition
from lab_generate_skill.adapters.sites.worker_client import SiteWorkerFailure
from lab_generate_skill.adapters.map_artifacts.site_access import OriginalMapSiteAccess
from lab_generate_skill.adapters.map_artifacts.site_storage import (
    OriginalMapStateStorage,
)
from lab_generate_skill.bootstrap.site_instance import build_site_instance
from map_registered_worker_fixtures import RegisteredMapCase
from test_map_registered_worker import registered_map
from site_instance_fixtures import node_path
from test_site_resource import enter
from test_slurm_commands import guard
from lab_generate_skill.adapters.slurm.step_launch import fixed_site_step_argv


@pytest.mark.parametrize(
    "change",
    [
        "old_schema",
        "old_provider",
        "missing",
        "foreign_site",
        "owner",
        "source",
        "split",
        "file_plan",
        "overlap",
        "escape",
        "runtime_overlap",
        "budget",
        "hash",
        "executable",
    ],
)
def test_bad_map_worker_declarations_before_any_effect(
    registered_map: RegisteredMapCase, change: str
) -> None:
    c = registered_map
    cfg = c.configuration
    raw = cfg.model_dump()
    original = cfg.map_inputs
    assert original is not None
    inputs = original.model_dump()
    if change == "old_schema":
        raw["schema_version"] = "site-worker-configuration/5"
    elif change == "old_provider":
        raw["token"]["provider_version"] = "5"
    elif change == "missing":
        raw["map_inputs"] = None
    elif change == "foreign_site":
        raw["site_id"] = "shopping_admin"
    elif change == "owner":
        inputs["scope"]["owner"]["worker_id"] = "other"
    elif change == "source":
        inputs["scope"]["task"]["source_task_id"] = "other"
    elif change == "split":
        inputs["scope"]["task"]["split"] = "test"
    elif change == "file_plan":
        raw["files"]["node_root"] = "/tmp/other-map"
    elif change == "overlap":
        inputs["artifact_root"] = inputs["evidence_root"]
    elif change == "escape":
        inputs["artifact_root"] = "/tmp/escaped-files"
    elif change == "runtime_overlap":
        inputs["artifact_root"] = inputs["runtime"]["trees"][0]["source_root"]
    elif change == "budget":
        inputs["max_file_bytes"] = inputs["max_total_bytes"] + 1
    elif change == "hash":
        inputs["private_input_sha256"] = "not-a-hash"
    elif change == "executable":
        raw["apptainer"] = "/other/apptainer"
    if change != "missing":
        raw["map_inputs"] = inputs
    with pytest.raises(ValueError):
        SiteWorkerConfiguration.model_validate(raw)
    assert (
        not Path(cfg.files.node_root).exists()
        and not Path(original.artifact_root).exists()
    )


def test_dispatch_requires_live_original_guard_and_creates_no_files(
    registered_map: RegisteredMapCase,
) -> None:
    c = registered_map
    with pytest.raises(ValueError):
        build_site_instance(c.configuration)
    assert c.configuration.map_inputs is not None
    assert not Path(c.configuration.map_inputs.artifact_root).exists()


@pytest.mark.parametrize("change", ["root", "budget", "scope", "resource", "producer"])
def test_foreign_full_file_plan_cannot_reuse_original_authority(
    registered_map: RegisteredMapCase, change: str
) -> None:
    c = registered_map
    with enter(c.resource):
        assert c.worker is not None and isinstance(
            c.worker.storage, OriginalMapStateStorage
        )
        access = c.worker.storage.access
        original = access.plan(c.request("snapshot"), guard())
        if change == "root":
            altered = original.model_copy(
                update={"private_root": str(c.workspace / "other")}
            )
        elif change == "budget":
            altered = original.model_copy(update={"max_files": original.max_files + 1})
        elif change == "scope":
            altered = original.model_copy(
                update={
                    "scope": original.scope.model_copy(update={"context_id": "other"})
                }
            )
        elif change == "resource":
            altered = original.model_copy(
                update={
                    "token": original.token.model_copy(
                        update={"expected_resource_id": "other"}
                    )
                }
            )
        else:
            altered = original.model_copy(update={"producer": "browser_process"})
        with pytest.raises((OwnershipConflict, ValueError)):
            access.verify(altered, "initialize", guard())
        assert not Path(original.private_root).exists()


def test_operation_identity_and_owner_and_unknown_phase_rejected(
    registered_map: RegisteredMapCase,
) -> None:
    c = registered_map
    with enter(c.resource):
        assert c.worker is not None and isinstance(
            c.worker.storage, OriginalMapStateStorage
        )
        access = c.worker.storage.access
        request = c.request("snapshot")
        plan = access.plan(request, guard())
        changed = request.model_copy(
            update={"binding_ref": c.put(b"other", "task-binding/1")}
        )
        with pytest.raises(OwnershipConflict):
            access.plan(changed, guard())
        with ThreadPoolExecutor() as pool:
            with pytest.raises(OwnershipConflict):
                pool.submit(access.verify, plan, "read", guard()).result()
        bad: Any = "execute_task"
        with pytest.raises(OwnershipConflict):
            access.verify(plan, bad, guard())


@pytest.mark.parametrize("kind", ["mount_id", "user_inode", "guard"])
def test_original_kernel_and_live_guard_are_rechecked_on_write(
    registered_map: RegisteredMapCase, kind: str
) -> None:
    c = registered_map
    with enter(c.resource):
        assert c.worker is not None and isinstance(
            c.worker.storage, OriginalMapStateStorage
        )
        access = c.worker.storage.access
        plan = access.plan(c.request("snapshot"), guard())
        original = c.reader.read(c.configuration, guard())
        member = original.acquired.details.ready.controller.target.worker
        if kind == "guard":
            c.live.value = c.owner_guard.model_copy(
                update={
                    "worker": c.owner_guard.worker.model_copy(
                        update={"start_ticks": c.owner_guard.worker.start_ticks + 1}
                    )
                }
            )
        else:
            c.member_change[kind] = getattr(member, kind) + 100
        if kind == "mount_id":
            access.verify(plan, "write", guard())
        else:
            with pytest.raises(OwnershipConflict):
                access.verify(plan, "write", guard())
        # Restore only explicit synthetic observations so original close can run.
        c.member_change.clear()
        c.live.value = c.owner_guard


def test_original_map_root_collision_never_reused(
    registered_map: RegisteredMapCase,
) -> None:
    c = registered_map
    inputs = c.configuration.map_inputs
    assert inputs is not None
    root = Path(inputs.artifact_root)
    root.mkdir(mode=0o700)
    marker = root / "original"
    marker.write_bytes(b"keep original")
    with pytest.raises(SiteWorkerFailure) as caught:
        with enter(c.resource):
            pytest.fail("colliding Map root must not start")
    assert caught.value.reply.error is not None
    assert (
        marker.read_bytes() == b"keep original"
        and not Path(c.configuration.files.node_root).exists()
    )
    assert (
        c.worker is not None
        and c.worker.started
        and isinstance(c.worker.error, FileExistsError)
    )


def test_version6_fixed_site_launch_and_old_provider_rejection(
    registered_map: RegisteredMapCase,
) -> None:
    c = registered_map
    token = c.configuration.token
    argv = fixed_site_step_argv(
        token,
        c.resource.spec.slurm.execution,
        "a0535",
        python_executable="/trusted/python",
        srun_executable="/usr/bin/srun",
    )
    assert argv[-1] == "lab_generate_skill.bootstrap.site_worker"
    assert "--nodelist=a0535" in argv or ("--nodelist" in argv and "a0535" in argv)
    with pytest.raises(ValueError, match="scope and provider"):
        fixed_site_step_argv(
            token.model_copy(update={"provider_version": "5"}),
            c.resource.spec.slurm.execution,
            "a0535",
            python_executable="/trusted/python",
            srun_executable="/usr/bin/srun",
        )
