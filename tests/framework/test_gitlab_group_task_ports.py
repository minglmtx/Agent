"""All four original Group branches on shared delayed preparation/Reset ports.

No browser or Actor is started. Explicit unit physical/nonstart/source premises
do not qualify a real instance, original benchmark attempt or training source.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any
import hashlib

import pytest

from lab_generate_skill.adapters.sites.task_preparation import (
    TaskPreparationUnconfirmed,
)
from lab_generate_skill.adapters.sites.task_finalization import (
    TaskFinalizationUnconfirmed,
    RecordedTaskFinalization,
)
from lab_generate_skill.bootstrap.gitlab_group_task_preparation import (
    gitlab_group_task_preparation,
)
from lab_generate_skill.bootstrap.gitlab_group_task_finalization import (
    gitlab_group_task_finalization,
)
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.lifecycle import ClosureReceipt, OperationContext
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeIntent
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_finalization import (
    TaskFinalizationPlan,
    UnstartedTaskBrowser,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from gitlab_group_task_port_fixtures import GroupPortCase, group_port_case
from preparation_record_fixtures import put
from site_instance_fixtures import node_path as node_path
from test_gitlab_group_complete_starts import PINS, W


@pytest.fixture(params=tuple(PINS))
def p(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> Iterator[GroupPortCase]:
    import gitlab_group_fixtures as inputs

    source = str(request.param)
    monkeypatch.setattr(
        inputs,
        "FIXTURE",
        W
        / "experiments/sft-ordinary-source-bindings-v1/prepared/contracts"
        / (source + ".json"),
    )
    with group_port_case(tmp_path, node_path, monkeypatch, source) as case:
        yield case


class UnitCleanupRights:
    """Explicit synthetic premises over real persisted intents and native facts."""

    def __init__(self, p: GroupPortCase) -> None:
        self.p = p
        self.denied = False
        self.unstarted_calls = 0
        self.resume_calls = 0

    def verify(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskFinalizationPlan,
        references: tuple[EvidenceRef, ...],
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        assert plan == self.p.plan and declaration.scope == self.p.scope
        assert operation.mode == "cleanup"
        if self.denied:
            raise PermissionError("Explicit Group unit cleanup denial")

    def close_unstarted(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskFinalizationPlan,
        observed: UnstartedTaskBrowser,
        observed_ref: EvidenceRef,
        operation: OperationContext,
        control: OperationControl,
    ) -> ClosureReceipt:
        self.verify(plan, declaration, (observed_ref,), operation, control)
        assert observed.owner_phase == "not_constructed"
        assert observed.token == self.p.reset.attempt_allocations[0]
        assert (
            self.p.resource.evidence.read(observed_ref, control)
            == observed.model_dump_json().encode()
        )
        records = self.p.resource.journal.records(observed.token.owner, operation)
        assert not any(r.token == observed.token for r in records)
        self.unstarted_calls += 1
        return ClosureReceipt(
            token=observed.token,
            operation_id=operation.operation_id,
            status="closed",
            evidence=(observed_ref,),
        )

    def verify_resume(
        self,
        configuration: SiteWorkerConfiguration,
        request: SiteResumeRequest,
        intent_ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        assert configuration == self.p.resource.spec.configuration
        intent = SiteResumeIntent.model_validate_json(
            self.p.resource.evidence.read(intent_ref, control)
        )
        assert intent.request == request
        assert (
            intent.configuration_sha256
            == hashlib.sha256(configuration.model_dump_json().encode()).hexdigest()
        )
        if self.denied:
            raise PermissionError("Explicit Group unit resume denial")
        self.resume_calls += 1


def finalization(
    p: GroupPortCase,
) -> tuple[RecordedTaskFinalization, UnitCleanupRights]:
    declaration = TaskFinalizationPlan(
        scope=p.scope,
        browser_close_operation_id="group-close",
        restore_operation_id="group-restore",
        resume_operation_id="group-resume",
        qualification_operation_id="group-reset-facts",
        reset_operation_id="group-safe-reset",
    )
    rights = UnitCleanupRights(p)
    return (
        gitlab_group_task_finalization(
            p.plan,
            declaration,
            put(p.resource.evidence, declaration),
            p.reset,
            p.preparation,
            lambda: None,
            p.resource.journal,
            lambda: None,
            rights,
            rights,
            rights,
            p.resource.evidence,
            p.resource.controls,
        ),
        rights,
    )


def close_and_restore(
    p: GroupPortCase, finalizer: RecordedTaskFinalization
) -> EvidenceRef:
    close = p.cleanup("group-closing")
    closed = finalizer.close(p.plan, p.reset, close, p.resource.controls.bind(close))
    restore = p.cleanup("group-restoring")
    return finalizer.restore(p.plan, closed, restore, p.resource.controls.bind(restore))


def test_complete_Group4_delayed_native_preparation_and_full_nonstart_reset(
    p: GroupPortCase,
) -> None:
    assert p.site.phase == "new" and not p.resource.channels and not p.requests
    assert p.acquire() and len(p.resource.channels) == 1 and not p.requests
    assert p.prepare()
    assert [r.action for r in p.requests] == ["snapshot", "prepare"]
    state = p.preparation.state
    assert state.result is not None and state.environment is not None
    assert state.environment.checks.status == "pass"
    prepared = p.preparation.records.load(
        state.result.publication, p.declaration.prepare_operation
    )
    assert (
        prepared.scope == p.scope
        and prepared.task_binding_ref == p.declaration.task_binding_ref
    )
    for function in (p.acquire, p.prepare):
        with pytest.raises(DispatchAlreadyCommitted):
            function()
    finalizer, rights = finalization(p)
    ref = close_and_restore(p, finalizer)
    assert finalizer.state.reset is not None and finalizer.state.reset.status == "safe"
    assert finalizer.state.reset_ref == ref
    assert rights.unstarted_calls == rights.resume_calls == 1
    assert [r.action for r in p.requests] == ["snapshot", "prepare", "restore"]
    assert p.natives[0].task.snapshot is not None
    assert finalizer.state.phase == "restored"
    with pytest.raises(DispatchAlreadyCommitted):
        close_and_restore(p, finalizer)


def test_Group_source_denial_does_not_open_site_or_dispatch_native(
    p: GroupPortCase,
) -> None:
    p.authority.denied = True
    with pytest.raises(TaskPreparationUnconfirmed) as error:
        p.acquire()
    assert isinstance(error.value.primary, PermissionError)
    assert p.site.phase == "new" and not p.requests and not p.resource.channels
    with pytest.raises(DispatchAlreadyCommitted):
        p.acquire()


def test_Group_partial_publication_retains_prepare_and_restores_once(
    p: GroupPortCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    p.acquire()
    original = p.resource.evidence.put

    def fail(
        raw: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        if metadata.content_schema == "prepared-task/1":
            raise OSError("controlled Group prepared publication lost")
        return original(raw, metadata, control, exchange_id=exchange_id)

    with monkeypatch.context() as patch:
        patch.setattr(p.resource.evidence, "put", fail)
        with pytest.raises(TaskPreparationUnconfirmed) as error:
            p.prepare()
    assert error.value.phase == "publication" and error.value.prepare_result is not None
    finalizer, _ = finalization(p)
    close_and_restore(p, finalizer)
    assert finalizer.state.reset is not None and finalizer.state.reset.status == "safe"
    assert [r.action for r in p.requests] == ["snapshot", "prepare", "restore"]


def test_Group_snapshot_unknown_is_not_redispatched_or_promoted_safe(
    p: GroupPortCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    p.acquire()
    calls = 0
    original = p.site.tasks.execute_task

    def lost(request: SiteTaskRequest, *, control: OperationControl) -> SiteTaskResult:
        nonlocal calls
        calls += 1
        original(request, control=control)
        raise TimeoutError("controlled Group snapshot return lost")

    monkeypatch.setattr(p.site.tasks, "execute_task", lost)
    with pytest.raises(TaskPreparationUnconfirmed) as error:
        p.prepare()
    assert error.value.phase == "snapshot" and isinstance(
        error.value.primary, TimeoutError
    )
    with pytest.raises(DispatchAlreadyCommitted):
        p.prepare()
    finalizer, _ = finalization(p)
    with pytest.raises(TaskFinalizationUnconfirmed) as failed:
        close_and_restore(p, finalizer)
    assert isinstance(failed.value.primary, OwnershipConflict)
    assert calls == 1 and finalizer.state.reset is None
    assert [r.action for r in p.requests] == ["snapshot"]


def test_Group_cancel_after_snapshot_preserves_return_and_never_replays(
    p: GroupPortCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    p.acquire()
    cancelled = False
    original = p.site.tasks.execute_task

    def returned(
        request: SiteTaskRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        nonlocal cancelled
        result = original(request, control=control)
        cancelled = True
        return result

    class Control:
        def checkpoint(self) -> float:
            if cancelled:
                raise OperationStopped("CANCELLED", "unit-group-preparing")
            return 1.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    monkeypatch.setattr(p.site.tasks, "execute_task", returned)
    with pytest.raises(TaskPreparationUnconfirmed) as error:
        p.preparation.prepare(p.plan, p.operation("preparing"), Control())
    assert isinstance(error.value.primary, OperationStopped)
    assert error.value.snapshot_result is not None
    assert [r.action for r in p.requests] == ["snapshot"]
    with pytest.raises(DispatchAlreadyCommitted):
        p.prepare()
    finalizer, _ = finalization(p)
    with pytest.raises(TaskFinalizationUnconfirmed) as failed:
        close_and_restore(p, finalizer)
    assert isinstance(failed.value.primary, OwnershipConflict)
    assert finalizer.state.reset is None


@pytest.mark.parametrize("invalid", [None, "", {}, [], 1, True])
def test_Group_ports_refuse_missing_or_wrong_type_before_native(
    p: GroupPortCase, invalid: Any
) -> None:
    with pytest.raises((ValueError, TypeError)):
        gitlab_group_task_preparation(
            invalid,
            p.declaration,
            p.resource.spec,
            p.site,
            p.resource.journal,
            p.resource.evidence,
            p.resource.controls,
            invalid,
            p.authority,
        )
    assert not p.requests and not p.resource.channels
