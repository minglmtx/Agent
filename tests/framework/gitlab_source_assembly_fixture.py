"""Actual source/worker ports with synthetic services/SQL and real CAS/tree I/O.

No benchmark site, actual kernel namespace, Actor or original-source permission.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import pytest
import site_resource_fixtures
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeResult
from lab_generate_skill.domain.site_worker import SiteInstanceStarted
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.gitlab.tasks.group_resume import GroupResume
from gitlab_group_lifecycle_fixtures import case as native_case, Case as NativeCase
from gitlab_source_selection import GitlabSourceSelection, group_selection
from gitlab_site_native_plan import native_configuration, private_site_plan
from qualified_source_native import QualifiedSource, configure_qualification
from site_resource_fixtures import Case as SiteCase, ResourceInstance, resource_case
from site_worker_fixtures import configuration
from generator_worker_fixtures import unit_guard
from source_browser_fixture import unit_source_browsers
from test_site_resource import enter
from test_slurm_commands import guard


@dataclass
class SourceCase:
    source: QualifiedSource
    native: NativeCase
    site: SiteCase
    browsers: list[Any]

    def request(self, action: str, snapshot: Any = None) -> SiteTaskRequest:
        n = self.source.native
        operation = self.site.op.model_copy(
            update={
                "operation_id": "native-task-" + action,
                "attempt_id": n.attempt_id,
                "recovery_ref": n.recovery_ref,
                "deadline": datetime.now(timezone.utc) + timedelta(seconds=30),
            }
        )
        if action == "restore":
            assert n.request is not None
            operation = n.request.operation.cleanup(
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
                "operation": operation,
            }
        )


@contextmanager
def selected_group_source(
    root: Path, node: Path, patch: pytest.MonkeyPatch
) -> Iterator[SourceCase]:
    selected = group_selection()
    base = configuration(job_id="4752096")
    private = private_site_plan(
        base.token.owner,
        base.installation,
        evidence_root=root / "evidence",
        session_root=root / "sessions",
        journal_root=root / "journal",
        selection=selected,
    )
    config = native_configuration(
        base.installation,
        job_id=base.token.owner.job_id,
        parent=node,
        private_evidence=private,
    )
    c = resource_case(root, patch, config=config)
    policy = configure_qualification(c, gitlab_selection=selected)
    worker = native_case(
        node,
        configured=c.spec.configuration,
        owner_guard=unit_guard(current_process_identity(), guard()),
    )
    worker.artifacts.store = c.evidence
    browsers: list[Any] = []

    class GroupInstance(ResourceInstance):
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
            return GroupResume(worker.task).resume_frontend(request, control=control)

        def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
            self.calls.append("stop")
            return worker.task.instance.stop(control)

    patch.setattr(site_resource_fixtures, "ResourceInstance", GroupInstance)
    unit_source_browsers(patch, browsers)
    try:
        with enter(c) as live:
            yield SourceCase(
                QualifiedSource(c, live, policy, gitlab_selection=selected),
                worker,
                c,
                browsers,
            )
    finally:
        worker.task.instance.stop(guard())
