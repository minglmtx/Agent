"""Shared source lifecycle with synthetic kernel/SQL/browser effects and real records."""

from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.domain.site_worker import SiteInstanceStarted
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeResult
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.reddit.tasks.image_resume import ImageResume
from qualified_source_native import QualifiedSource, configure_qualification
from reddit_image_lifecycle_fixtures import case as native_case, Case as NativeCase
from reddit_services_fixtures import Group
from reddit_site_native_plan import native_configuration, private_site_plan
from site_worker_fixtures import configuration
from site_resource_fixtures import resource_case, ResourceInstance, Case as SiteCase
from browser_resource_fixtures import resource_case as browser_case
from test_site_resource import enter
from test_slurm_commands import guard
from source_browser_fixture import unit_source_browsers
from reddit_source_selection import RedditSourceSelection
import site_resource_fixtures
import prepared_browser_native


@dataclass
class SourceCase:
    source: QualifiedSource
    native: NativeCase
    site: SiteCase
    browsers: list[Any]

    def request(self, action: str, snapshot: Any = None) -> SiteTaskRequest:
        n = self.source.native
        op = self.site.op.model_copy(
            update={
                "operation_id": "native-task-" + action,
                "attempt_id": n.attempt_id,
                "recovery_ref": n.recovery_ref,
                "deadline": datetime.now(timezone.utc) + timedelta(seconds=30),
            }
        )
        if action == "restore":
            assert n.request is not None
            op = n.request.operation.cleanup(
                "native-task-restore", now=datetime.now(timezone.utc), seconds=30
            )
        return SiteTaskRequest.model_validate(
            {
                **self.native.request.model_dump(),
                "task": n.public.identity,
                "binding_ref": n.binding_ref,
                "private_input": n.private_input_json(),
                "action": action,
                "snapshot_ref": snapshot,
                "operation": op,
            }
        )


@contextmanager
def shared_source(
    root: Path,
    node: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    selection: RedditSourceSelection | None = None,
) -> Iterator[SourceCase]:
    host, original_pin = current_process_identity(), Group.pin_namespace

    def pin(group: Group, name: str, control: Any) -> Any:
        value = original_pin(group, name, control)
        value = value.model_copy(
            update={
                key: getattr(value, key).model_copy(
                    update={
                        "node_id": host.node_id,
                        "boot_id": host.boot_id,
                        "start_ticks": host.start_ticks + offset + group.generation,
                    }
                )
                for key, offset in (("launcher", 10), ("init", 20))
            }
        )
        group.pins[-1] = value
        return value

    monkeypatch.setattr(Group, "pin_namespace", pin)
    base = configuration(job_id="4752096")
    private = private_site_plan(
        base.token.owner,
        base.installation,
        evidence_root=root / "evidence",
        session_root=root / "sessions",
        journal_root=root / "journal",
    )
    config = native_configuration(
        base.installation,
        job_id=base.token.owner.job_id,
        parent=node,
        private_evidence=private,
    )
    c = resource_case(root, monkeypatch, config=config)
    policy = configure_qualification(c, reddit_selection=selection)
    worker = native_case(node, configured=c.spec.configuration)
    worker.artifacts.store = c.evidence
    browsers: list[Any] = []

    class NativeInstance(ResourceInstance):
        def start(self, control: OperationControl) -> SiteInstanceStarted:
            super().start(control)
            return worker.artifacts.context.instance

        def execute_task(
            self, request: SiteTaskRequest, *, control: OperationControl
        ) -> SiteTaskResult:
            return worker.task.execute_task(request, control=control)

        def capture_task(
            self, request: SiteCaptureRequest, *, control: OperationControl
        ) -> SiteTaskResult:
            return worker.task.capture_task(request, control=control)

        def resume_frontend(
            self, request: SiteResumeRequest, *, control: OperationControl
        ) -> SiteResumeResult:
            return ImageResume(worker.task).resume_frontend(request, control=control)

        def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
            self.calls.append("stop")
            return worker.task.instance.stop(control)

    monkeypatch.setattr(site_resource_fixtures, "ResourceInstance", NativeInstance)

    unit_source_browsers(monkeypatch, browsers)
    try:
        with enter(c) as live:
            yield SourceCase(
                QualifiedSource(c, live, policy, reddit_selection=selection),
                worker,
                c,
                browsers,
            )
    finally:
        worker.task.instance.stop(guard())
