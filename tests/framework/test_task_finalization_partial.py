"""Genuine partial preparation; original unknown remains, only owned cleanup."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.sites.task_preparation import (
    TaskPreparationUnconfirmed,
)
from lab_generate_skill.adapters.sites.task_finalization import (
    TaskFinalizationUnconfirmed,
)
from lab_generate_skill.bootstrap.map_task_finalization import map_task_finalization
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OperationStopped
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.lifecycle import ClosureReceipt, OperationContext
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_finalization import (
    TaskFinalizationPlan,
    UnstartedTaskBrowser,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from map_task_preparation_port_fixtures import preparation_case, MapPreparationPortCase
from preparation_record_fixtures import put
from site_instance_fixtures import node_path as node_path
from task_finalization_port_fixtures import (
    UnitFinalizationAuthority,
    UnitResumeAuthority,
)


class NoBrowserConstructed:
    """Explicit synthetic exclusive factory premise, never production permission."""

    def __init__(self, p: MapPreparationPortCase) -> None:
        self.p, self.calls = p, 0

    def close_unstarted(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskFinalizationPlan,
        observed: UnstartedTaskBrowser,
        observed_ref: EvidenceRef,
        operation: OperationContext,
        control: OperationControl,
    ) -> ClosureReceipt:
        control.checkpoint()
        assert plan == self.p.plan and observed.owner_phase == "not_constructed"
        assert (
            self.p.original.resource.evidence.read(observed_ref, control)
            == observed.model_dump_json().encode()
        )
        assert self.p.preparation.state.phase == "quarantined"
        # This test has no browser factory, acquisition call, worker or handle.
        self.calls += 1
        return ClosureReceipt(
            token=observed.token,
            operation_id=operation.operation_id,
            status="closed",
            evidence=(observed_ref,),
        )


@pytest.mark.parametrize(
    "fault",
    [
        "prepare-not-dispatched",
        "prepare-return-lost",
        "snapshot-return-lost",
        "prepared-publication-lost",
    ],
)
def test_partial_preparation_preserves_original_unknown_and_only_restores_qualified_prefix(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with preparation_case(node_path, monkeypatch) as p:
        p.acquire()
        original = p.site.tasks.execute_task

        def fail(request: Any, **kwargs: Any) -> Any:
            if request.action == "prepare" and fault == "prepare-not-dispatched":
                raise OperationStopped("CANCELLED", request.operation.operation_id)
            value = original(request, **kwargs)
            if fault in (
                "snapshot-return-lost",
                "prepare-return-lost",
            ) and request.action == (
                "snapshot" if fault == "snapshot-return-lost" else "prepare"
            ):
                raise TimeoutError("Synthetic original preparation return lost")
            return value

        store = p.original.resource.evidence
        original_put = store.put

        def lose_publication(
            raw: bytes,
            metadata: EvidenceMetadata,
            control: OperationControl | None = None,
        ) -> EvidenceRef:
            ref = original_put(raw, metadata, control)
            if (
                metadata.content_schema == "site-task-prepared/2"
                and fault == "prepared-publication-lost"
            ):
                raise TimeoutError("Synthetic complete prepared publication ack lost")
            return ref

        with monkeypatch.context() as patch:
            patch.setattr(p.site.tasks, "execute_task", fail)
            patch.setattr(store, "put", lose_publication)
            with pytest.raises(TaskPreparationUnconfirmed) as caught:
                p.prepare()
        original_failure = caught.value
        assert p.preparation.state.phase == "quarantined"
        assert p.preparation.state.result_ref is None
        d = TaskFinalizationPlan(
            scope=p.reset.scope,
            browser_close_operation_id="partial-browser-close",
            restore_operation_id="partial-native-restore",
            resume_operation_id="partial-native-resume",
            qualification_operation_id="partial-reset-facts",
            reset_operation_id="partial-safe-reset",
        )
        source, resume, unstarted = (
            UnitFinalizationAuthority(p),
            UnitResumeAuthority(p),
            NoBrowserConstructed(p),
        )
        f = map_task_finalization(
            p.plan,
            d,
            put(p.original.resource.evidence, d),
            p.reset,
            p.preparation,
            lambda: None,
            p.original.resource.journal,
            lambda: None,
            source,
            unstarted,
            resume,
            p.original.resource.evidence,
            p.original.resource.controls,
        )
        source.finalizer = resume.finalizer = f

        def op(name: str) -> OperationContext:
            return p.plan.operation.cleanup(
                "partial-" + name,
                now=datetime.now(timezone.utc),
                seconds=p.plan.cleanup_seconds,
            )

        closing = op("closing")
        closed = f.close(
            p.plan, p.reset, closing, p.original.resource.controls.bind(closing)
        )
        assert unstarted.calls == 1 and all(
            c.status == "closed" for c in closed.closures
        )
        restoring = op("restoring")
        control = p.original.resource.controls.bind(restoring)
        if fault != "prepared-publication-lost":
            before = len(p.requests)
            with pytest.raises(TaskFinalizationUnconfirmed):
                f.restore(p.plan, closed, restoring, control)
            assert (
                len(p.requests) == before
                and resume.calls == 0
                and f.state.reset_ref is None
            )
        else:
            f.restore(p.plan, closed, restoring, control)
            assert f.state.reset is not None and f.state.reset.status == "safe"
            assert [r.action for r in p.requests] == ["snapshot", "prepare", "restore"]
            assert resume.calls == 1
        with pytest.raises(DispatchAlreadyCommitted):
            f.restore(p.plan, closed, restoring, control)
        assert (
            caught.value is original_failure
            and p.preparation.state.phase == "quarantined"
        )
        assert p.preparation.state.result_ref is None
