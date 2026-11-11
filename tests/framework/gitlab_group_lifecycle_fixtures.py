"""File-backed SQL doubles with real complete fixture-tree copy/restore and CAS."""

import hashlib
import json
import os
import shutil
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.bootstrap.gitlab_group_state import load_group_state
from lab_generate_skill.bootstrap.gitlab_group_capture import load_group_capture
from lab_generate_skill.bootstrap.site_private_artifacts import (
    _IndependentCleanupControls,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.site_worker import (
    SiteInstanceStarted,
    SiteWorkerConfiguration,
)
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceContext
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.native_private_json import GITLAB_GROUP_PRIVATE_JSON
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.gitlab.instance import GitlabInstance
from lab_generate_skill.sites.gitlab.snapshot import GitlabInventory
from lab_generate_skill.sites.gitlab.snapshot_programs import INVENTORY
from lab_generate_skill.sites.gitlab.group_native_reader import GitlabGroupNativeReader
from lab_generate_skill.sites.gitlab.group_sql_capture import GROUP_CAPTURE
from lab_generate_skill.sites.gitlab.project_copy import (
    GitlabProjectCopyReader,
    PROJECT_ARGV,
)
from lab_generate_skill.sites.gitlab.group_capture_reader import GroupCaptureReader
from lab_generate_skill.sites.gitlab.tasks.group_lifecycle import GroupLifecycle
from gitlab_native_fixtures import Commands, Files, Ports, Group, plan
from gitlab_group_service_fixtures import OriginalFixtureGroup
from gitlab_group_fixtures import native_state, selected_spec
from gitlab_ssh_lifecycle_fixtures import Artifacts
from site_worker_fixtures import configuration
from generator_worker_fixtures import unit_guard
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from test_gitlab_ssh_key_inputs import reference
from test_slurm_commands import guard

PROJECTS = b'1,10,"Original, project",original\n2,10,"Line\nbreak",second\n'


class TreeCommands(Commands):
    def inventory_at(self, path: Path) -> GitlabInventory:
        rows: list[tuple[object, ...]] = []
        files = directories = links = size = 0

        def visit(item: Path, relative: str) -> None:
            nonlocal files, directories, links, size
            info = item.lstat()
            mode = stat.S_IMODE(info.st_mode)
            if item.is_symlink():
                assert (
                    relative == "data/nginx/logs"
                    and os.readlink(item) == "/var/log/gitlab/nginx"
                )
                links += 1
                rows.append((relative, "symlink", mode, os.readlink(item)))
            elif item.is_dir():
                directories += 1
                rows.append((relative, "directory", mode))
                for child in sorted(item.iterdir()):
                    visit(child, str(child.relative_to(path)))
            else:
                raw = item.read_bytes()
                files += 1
                size += len(raw)
                rows.append(
                    (relative, "file", mode, len(raw), hashlib.sha256(raw).hexdigest())
                )

        visit(path, "")
        return GitlabInventory(
            sha256=hashlib.sha256(
                json.dumps(rows, separators=(",", ":")).encode()
            ).hexdigest(),
            files=files,
            directories=directories,
            symlinks=links,
            bytes=size,
        )

    def run(self, argv: tuple[str, ...], control: OperationControl) -> bytes:
        if INVENTORY not in argv and "/bin/cp" not in argv:
            return super().run(argv, control)
        control.checkpoint()
        self.calls.append(argv)
        if self.error is not None and self.error in argv:
            raise self.failure
        state, saved = self.root / "state", self.root / "snapshot/state"
        if "/bin/cp" in argv:
            if argv[-2:] == ("/state", "/snapshot/state"):
                shutil.copytree(state, saved, symlinks=True)
            else:
                assert argv[-2:] == ("/snapshot/state/.", "/state")
                shutil.copytree(saved, state, symlinks=True, dirs_exist_ok=True)
            return b""
        path = saved if argv[-1] == "/snapshot/state" else state
        result = self.inventory_at(path)
        if argv[-1] == "clear":
            for child in state.iterdir():
                if child.is_symlink() or child.is_file():
                    child.unlink()
                else:
                    shutil.rmtree(child)
        return result.model_dump_json().encode()


class SqlReplies:
    def __init__(self, state: Path) -> None:
        self.state = state
        self.calls: list[tuple[tuple[str, ...], bytes]] = []
        self.error: BaseException | None = None
        self.fail_part: str | None = None

    def run_input(
        self, argv: tuple[str, ...], data: bytes, control: OperationControl
    ) -> bytes:
        control.checkpoint()
        self.calls.append((argv, data))
        group = argv[-2:] == ("-e", GROUP_CAPTURE)
        if self.error is not None and (
            self.fail_part is None
            or self.fail_part == ("groups" if group else "projects")
        ):
            raise self.error
        if group:
            with_settings = json.loads(data)["with_settings"]
            assert type(with_settings) is bool
            raw = (self.state / "group.json").read_bytes()
            if with_settings:
                return raw
            state = json.loads(raw)
            state["settings"] = None
            return json.dumps(state).encode()
        assert argv[-len(PROJECT_ARGV) :] == PROJECT_ARGV and data == b"\n"
        return (self.state / "projects.csv").read_bytes()


@dataclass
class Case:
    task: GroupLifecycle
    sql: SqlReplies
    commands: TreeCommands
    artifacts: Artifacts
    request: SiteTaskRequest
    state: Path

    def next(
        self, action: str, name: str, *, snapshot_ref: EvidenceRef | None = None
    ) -> SiteTaskRequest:
        task = self.task
        assert task.snapshot is not None
        parent = task.preparation or task.snapshot.request
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
                "operation": self.request.operation.model_copy(
                    update={
                        "operation_id": name,
                        "mode": "cleanup" if action == "restore" else "execute",
                        "parent_operation_id": (
                            parent.operation.operation_id
                            if action == "restore"
                            else None
                        ),
                    }
                ),
            }
        )


def case(
    root: Path,
    *,
    configured: SiteWorkerConfiguration | None = None,
    owner_guard: ProcessOwnerGuard | None = None,
) -> Case:
    node = root / "instance"
    commands = TreeCommands(node)
    groups: list[Group] = []

    def services(logs: str, control: OperationControl) -> Group:
        control.checkpoint()
        value = OriginalFixtureGroup(len(groups), owner_guard)
        groups.append(value)
        return value

    instance = GitlabInstance(
        plan(node),
        database_peer_user="native_user",
        files=Files(),
        ports=Ports(),
        commands=commands,
        services=services,
    )
    if configured is not None:
        instance.files_plan = configured.files
    instance.prepare(guard())
    endpoint = instance.start(guard())
    assert instance.spec is not None and instance.lease is not None
    state = Path(instance.files_plan.state_root)
    (state / "data/nginx").mkdir(parents=True)
    (state / "data/nginx/logs").symlink_to("/var/log/gitlab/nginx")
    (state / "group.json").write_bytes(native_state().model_dump_json().encode())
    (state / "projects.csv").write_bytes(PROJECTS)
    base = configuration() if configured is None else configured
    token = base.token.model_copy(
        update={"expected_resource_id": instance.files_plan.instance_id}
    )
    context = SitePrivateEvidenceContext(
        configuration_sha256=(
            "a" * 64
            if configured is None
            else hashlib.sha256(configured.model_dump_json().encode()).hexdigest()
        ),
        token=token,
        instance=SiteInstanceStarted(
            files=instance.files_plan, endpoint=endpoint, ports=instance.lease.ports
        ),
        owner_guard=owner_guard or unit_guard(current_process_identity(), guard()),
    )
    artifacts = Artifacts(
        root / "private-evidence", context, profile=GITLAB_GROUP_PRIVATE_JSON
    )
    sql = SqlReplies(state)
    reader = GroupCaptureReader(
        GitlabGroupNativeReader(instance.spec, sql, load_group_state),
        GitlabProjectCopyReader(instance.spec, sql, SystemClock()),
        load_group_capture,
    )
    request = SiteTaskRequest(
        task=selected_spec().task,
        binding_ref=reference(b"{}", content_schema="task-binding/1"),
        operation=OperationContext(
            operation_id="group-snapshot",
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
        GroupLifecycle(
            instance,
            reader,
            lambda c: "native-user",
            artifacts,
            clock=SystemClock(),
            cleanup_controls=_IndependentCleanupControls(),
        ),
        sql,
        commands,
        artifacts,
        request,
        state,
    )
