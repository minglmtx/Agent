"""Source initializer original ports and partial failure; native/kernel are unit."""

from pathlib import Path
from lab_generate_skill.domain.source_recovery_budget import SourceRecoveryBudgets
from collections.abc import Iterator
from typing import Any
from dataclasses import replace
import pytest
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.bootstrap.map_source_qualification import (
    qualify_map_navigation_source,
    MapSourceQualificationUnconfirmed,
)
from lab_generate_skill.bootstrap.map_source_measurement import SourceBrowserAssets
from lab_generate_skill.bootstrap.map_source_records import MapSourceRecords
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRequirements
from lab_generate_skill.domain.lifecycle import AllocationToken, OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.tasks.navigation_spec import NavigationSpec
from map_registered_worker_fixtures import RegisteredMapCase
from map_navigation_evaluation_fixtures import bind_original_contract
from map_qualification_fixtures import configure_qualification
from map_navigation_source_fixtures import selection
from browsergym_fixtures import CHROMIUM
from browser_worker_fixtures import LIBS
from site_instance_fixtures import node_path as node_path
from site_resource_fixtures import ResourceChannel
import lab_generate_skill.bootstrap.map_source_qualification as module


@pytest.mark.parametrize("value", [None, "source", 0, True, {}, []])
def test_source_initializer_requires_explicit_typed_inputs_before_effects(
    value: Any,
) -> None:
    with pytest.raises(TypeError):
        qualify_map_navigation_source(
            value,
            value,
            value,
            value,
            value,
            value,
            journal=value,
            controls=value,
            clock=value,
            prefix="source",
            metadata_seconds=1,
        )


def test_source_browser_asset_policy_rejects_illegal_values_before_source_start() -> (
    None
):
    assets = SourceBrowserAssets(
        CHROMIUM,
        CHROMIUM.rsplit("/", 3)[0],
        (LIBS,),
        0,
        10000,
        4096,
        EvidenceRequirements(events=("terminal",)),
    )
    changes: tuple[dict[str, Any], ...] = (
        {"chromium_executable": "relative"},
        {"library_directories": (LIBS, LIBS)},
        {"seed": True},
        {"seed": -1},
        {"action_timeout_ms": 499},
        {"max_events": 4097},
        {"requirements": {}},
        {"requirements": EvidenceRequirements(events=("download",))},
    )
    for change in changes:
        with pytest.raises((TypeError, ValueError)):
            replace(assets, **change)


@pytest.fixture
def source_case(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[
    tuple[RegisteredMapCase, OriginalSourceQualificationOwner, SourceBrowserAssets]
]:
    c = RegisteredMapCase(
        node_path, monkeypatch, navigation_source="125732d3658ab4daee02"
    )
    try:
        bind_original_contract(c)
        configure_qualification(c, monkeypatch)
        assert isinstance(c.private, NavigationSpec)
        # The real RPC runs in a different process. This in-process native
        # fixture must expose the worker only while servicing that RPC, then
        # restore the original controller for independent artifact reads.
        c.observer = "controller"
        exchange = ResourceChannel.exchange

        def worker_exchange(
            channel: ResourceChannel, payload: bytes, control: OperationControl
        ) -> bytes:
            previous = c.observer
            c.observer = "worker"
            try:
                return exchange(channel, payload, control)
            finally:
                c.observer = previous

        monkeypatch.setattr(ResourceChannel, "exchange", worker_exchange)

        class UnitOwner(OriginalSourceQualificationOwner):
            def require_caller(
                self, op: OperationContext, control: OperationControl
            ) -> None:
                control.checkpoint()
                if (op.run_id, op.owner_id) != (
                    self.scope.owner.run_id,
                    self.scope.owner.owner_id,
                ):
                    raise OwnershipConflict("Explicit unit source caller changed")

        # Explicit physical-observation premise. Original registered resource,
        # mandatory source permissions, RPCs, CAS and journals remain in use.
        # Production always constructs its actual ObservedSiteResourceAuthority.
        class UnitPhysical:
            def __init__(self, *args: Any, source: Any, **kwargs: Any) -> None:
                self.source = source

            def __enter__(self) -> "UnitPhysical":
                return self

            def __exit__(self, *args: Any) -> None:
                pass

            def __getattr__(self, name: str) -> Any:
                return getattr(self.source, name)

        monkeypatch.setattr(module, "ObservedSiteResourceAuthority", UnitPhysical)
        spec = c.resource.spec
        owner = UnitOwner(
            c.scope, spec.slurm.execution, spec.slurm.parent, c.resource.evidence
        )
        assets = SourceBrowserAssets(
            CHROMIUM,
            CHROMIUM.rsplit("/", 3)[0],
            (LIBS,),
            0,
            10000,
            4096,
            EvidenceRequirements(events=("terminal",)),
        )
        yield c, owner, assets
    finally:
        c.close_sockets()


def test_source_initializer_native_preparation_then_cancel_closes_original_site_and_never_publishes_context(
    source_case: tuple[
        RegisteredMapCase, OriginalSourceQualificationOwner, SourceBrowserAssets
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c, owner, assets = source_case
    assert isinstance(c.private, NavigationSpec)
    spec = c.resource.spec
    seen: list[MapSourceRecords] = []

    def cancelled(
        records: MapSourceRecords,
        token: AllocationToken,
        value: SourceBrowserAssets,
        *,
        operation_seconds: int,
    ) -> None:
        assert operation_seconds == 120
        assert records.progress.publication is not None
        assert records.progress.prepare_request is not None
        assert records.progress.prepare_result is not None
        assert records.progress.environment is not None
        assert records.progress.environment.checks.status == "pass"
        assert records.progress.reset_plan is not None
        assert token == records.progress.reset_plan.attempt_allocations[0]
        seen.append(records)
        raise PermissionError(
            "Explicit initial browser cancellation after actual fixture preparation"
        )

    monkeypatch.setattr(module, "measure_map_source", cancelled)
    with pytest.raises(MapSourceQualificationUnconfirmed) as caught:
        qualify_map_navigation_source(
            owner,
            spec,
            c.resource.op,
            selection("125732d3658ab4daee02"),
            c.private,
            assets,
            journal=c.resource.journal,
            controls=c.resource.controls,
            clock=c.resource.clock,
            prefix="source-only-unit",
            metadata_seconds=120,
        )
    error = caught.value
    import traceback

    if not seen:
        traceback.print_exception(error.primary)
        for cleanup_error in error.cleanup_errors:
            traceback.print_exception(cleanup_error)
        print("Source initializer phase:", error.progress.phase)
    assert len(seen) == 1 and isinstance(error.primary, PermissionError)
    assert error.cleanup_errors == () and not error.actual_actor_dispatched
    assert (
        error.progress.snapshot_ref is not None
        and error.progress.publication is not None
    )
    assert error.progress.baseline is None and error.progress.reset is None
    assert error.progress.browser is None and not error.progress.restore_attempted
    cleanup = c.resource.op.cleanup(
        "source-final-read", now=c.resource.clock.utcnow(), seconds=30
    )
    assert c.resource.journal.read(spec.token, cleanup).state == "closed"


@pytest.mark.parametrize(
    "cancel_after_reset,lose_restore_return",
    [(False, False), (True, False), (False, True)],
)
def test_source_initializer_unique_initial_observation_restore_reset_and_close_before_publication(
    source_case: tuple[
        RegisteredMapCase, OriginalSourceQualificationOwner, SourceBrowserAssets
    ],
    monkeypatch: pytest.MonkeyPatch,
    cancel_after_reset: bool,
    lose_restore_return: bool,
    recovery_budgets: SourceRecoveryBudgets | None = None,
    use_publication_root: bool = False,
    expire_acquisition: bool = False,
    source_reads: Any = None,
) -> None:
    from types import SimpleNamespace
    from lab_generate_skill.adapters.browsergym.retained_resource import (
        RetainedBrowserResource,
    )
    from lab_generate_skill.adapters.browsergym.source_qualification_authority import (
        SourceQualificationBrowserAuthority,
    )
    from lab_generate_skill.domain.browser_resource import (
        BrowserResourceSpec,
        BrowserResourceAttempt,
    )
    from lab_generate_skill.domain.browser_step import BrowserStepClosed
    from lab_generate_skill.domain.browser_worker_acquisition import (
        BrowserWorkerAcquiredFact,
    )
    from lab_generate_skill.domain.process_identity import ProcessTermination
    from lab_generate_skill.domain.lifecycle import ClosureReceipt
    from lab_generate_skill.bootstrap.map_source_publication import (
        ClosedMapQualificationFacts,
    )
    from map_navigation_browser_resource_fixtures import (
        navigation_browser_resource,
        NavigationBrowserDouble,
    )
    import lab_generate_skill.bootstrap.source_qualification_measurement as measurement
    import lab_generate_skill.adapters.browsergym.source_qualification_authority as browser_rights
    import lab_generate_skill.adapters.browsergym.source_qualification_observation as observation_rights

    c, owner, assets = source_case
    assert isinstance(c.private, NavigationSpec)
    from datetime import timedelta

    root = (
        c.resource.op.model_copy(
            update={
                "operation_id": "original-root",
                "allocation_id": None,
                "recovery_ref": None,
                "deadline": c.resource.op.deadline + timedelta(seconds=120),
            }
        )
        if use_publication_root
        else None
    )
    backends: list[NavigationBrowserDouble] = []
    authorities: list[SourceQualificationBrowserAuthority] = []
    retained: list[RetainedBrowserResource] = []
    published: list[ClosedMapQualificationFacts] = []

    # These are explicit page/process/kernel premises only. The new passive
    # capture, original persisted acquisition/seq0 relationships, native
    # restore/resume and complete Reset checks execute their production code.
    class UnitBrowser(SourceQualificationBrowserAuthority):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            authorities.append(self)

        def verify_closed(
            self,
            spec: BrowserResourceSpec,
            attempt: BrowserResourceAttempt,
            ending: ProcessTermination | None,
            step: BrowserStepClosed | None,
            op: OperationContext,
            control: OperationControl,
        ) -> ClosureReceipt:
            self.owner.require(op, control, new_work=False)
            return backends[0].resource.authority.verify_closed(
                spec, attempt, ending, step, op, control
            )

    def kernel(*args: Any, **kwargs: Any) -> Any:
        resource = backends[0].resource
        record = resource.journal.read(resource.spec.token, resource.op)
        fact = BrowserWorkerAcquiredFact.model_validate_json(
            resource.evidence.read(
                record.events[2].evidence[0], resource.controls.bind(resource.op)
            )
        )
        assert args[1] == fact.details.prepared.owner_guard.worker
        return SimpleNamespace(
            membership=fact.details.prepared.step.controller.target.worker
        )

    def browser(
        spec: BrowserResourceSpec,
        op: OperationContext,
        **kwargs: Any,
    ) -> RetainedBrowserResource:
        root = c.workspace / "source-browser"
        root.mkdir()
        backend = navigation_browser_resource(
            root,
            monkeypatch,
            configuration=spec.configuration,
            store=c.resource.evidence,
            declared_token=spec.token,
            site=c.resource.spec,
        )
        backend.resource.spec = spec
        backend.resource.op = op
        backend.resource.journal = c.resource.journal
        backends.append(backend)
        assert kwargs["cleanup_seconds"] == (
            120 if recovery_budgets is None else recovery_budgets.browser_close_seconds
        )
        # This fixture has a shorter original parent deadline. Metadata budget
        # cannot extend that original execute operation.
        assert op.deadline == c.resource.op.deadline
        value = RetainedBrowserResource(spec, op, **kwargs)
        retained.append(value)
        return value

    def before_publish(
        selected_owner: OriginalSourceQualificationOwner,
        facts: ClosedMapQualificationFacts,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        assert selected_owner is owner
        assert args[0].deadline <= (root or c.resource.op).deadline
        assert args[0].cancellation_ref == c.resource.op.cancellation_ref
        assert facts.baseline.status == "ready" and facts.reset.status == "safe"
        assert facts.site_record.state == facts.browser_record.state == "closed"
        assert retained[0].phase == "closed"
        assert len(backends[0].engines) == 1
        assert backends[0].engines[0].sequence == 0
        published.append(facts)
        # Closed publication itself has independent real-graph evidence in
        # 4891904. This software native/page fixture cannot grant a live source.
        raise PermissionError("Explicit unit stop before real-source publication")

    monkeypatch.setattr(measurement, "SourceQualificationBrowserAuthority", UnitBrowser)
    monkeypatch.setattr(measurement, "RetainedBrowserResource", browser)
    monkeypatch.setattr(browser_rights, "observe_process_cgroup", kernel)
    monkeypatch.setattr(observation_rights, "observe_process_cgroup", kernel)
    monkeypatch.setattr(module, "publish_closed_map_qualification", before_publish)
    from lab_generate_skill.domain.errors import (
        OperationStopped,
        DispatchAlreadyCommitted,
    )
    from lab_generate_skill.adapters.storage.state_qualifications import (
        EvidenceStateQualifications,
    )
    from lab_generate_skill.bootstrap.map_source_recovery import restore_map_source
    from lab_generate_skill.bootstrap.source_qualification_records import (
        SourceQualificationRecords,
    )
    from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
    from lab_generate_skill.domain.evidence import EvidenceRef

    parent_control = c.resource.controls.bind(c.resource.op)

    def stopped() -> float:
        raise OperationStopped("CANCELLED", c.resource.op.operation_id)

    def restore_once(
        records: MapSourceRecords, qualifications: EvidenceStateQualifications
    ) -> None:
        restore_map_source(records, qualifications)
        references = tuple(records.progress.references)
        with pytest.raises(DispatchAlreadyCommitted):
            restore_map_source(records, qualifications)
        assert tuple(records.progress.references) == references
        if cancel_after_reset:
            monkeypatch.setattr(parent_control, "checkpoint", stopped)
        if expire_acquisition:

            def expired() -> float:
                raise OperationStopped("DEADLINE_EXCEEDED", c.resource.op.operation_id)

            monkeypatch.setattr(parent_control, "checkpoint", expired)

    monkeypatch.setattr(module, "restore_map_source", restore_once)
    if lose_restore_return:
        original_request = SourceQualificationRecords.request

        def lost(
            records: SourceQualificationRecords,
            action: str,
            operation: OperationContext,
        ) -> tuple[SiteTaskRequest, SiteTaskResult, EvidenceRef, EvidenceRef]:
            result = original_request(records, action, operation)
            if action == "restore":
                raise OSError(
                    "Original restore parent return lost after result persistence"
                )
            return result

        monkeypatch.setattr(SourceQualificationRecords, "request", lost)
    with pytest.raises(MapSourceQualificationUnconfirmed) as caught:
        qualify_map_navigation_source(
            owner,
            c.resource.spec,
            c.resource.op,
            selection("125732d3658ab4daee02"),
            c.private,
            assets,
            journal=c.resource.journal,
            controls=c.resource.controls,
            clock=c.resource.clock,
            prefix="source-only-unit",
            metadata_seconds=120,
            recovery_budgets=recovery_budgets,
            publication_root=root,
            source_reads=source_reads,
        )
    error = caught.value
    if not published and not cancel_after_reset and not lose_restore_return:
        import traceback

        traceback.print_exception(error.primary)
        for cleanup_error in error.cleanup_errors:
            traceback.print_exception(cleanup_error)
        print("Source initializer phase:", error.progress.phase)
    if lose_restore_return:
        assert not published and error.primary is None
        assert len(error.cleanup_errors) == 1 and isinstance(
            error.cleanup_errors[0], OSError
        )
        assert error.progress.restore_attempted and error.progress.reset is None
        read = c.resource.op.cleanup(
            "partial-restore-final-read", now=c.resource.clock.utcnow(), seconds=30
        )
        assert c.resource.journal.read(c.resource.spec.token, read).state == "closed"
        return
    if cancel_after_reset:
        assert not published and isinstance(error.primary, OperationStopped)
        assert error.primary.reason_code == "CANCELLED"
    else:
        assert len(published) == 1 and isinstance(error.primary, PermissionError)
    assert error.cleanup_errors == () and not error.actual_actor_dispatched
    assert error.progress.restore_attempted and error.progress.reset is not None
    assert error.progress.phase == "publishing-closed-source"
    read = c.resource.op.cleanup(
        "source-cancel-final-read", now=c.resource.clock.utcnow(), seconds=30
    )
    assert c.resource.journal.read(c.resource.spec.token, read).state == "closed"
