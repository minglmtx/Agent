"""Original source ports together; explicit synthetic native/page/kernel premises.

The real caller is observed, while no benchmark site or model is started. Stop
before source publication: this fixture cannot grant a real closed source.
"""

from datetime import datetime, timedelta, timezone
from lab_generate_skill.domain.actor_acquisition_inputs import ActorAcquisitionInputs
from lab_generate_skill.domain.preparation_read import PreparationReadRequest
from lab_generate_skill.domain.baseline_read import BaselineReadRequest
from lab_generate_skill.domain.source_recovery_budget import SourceRecoveryBudgets
import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
import pytest

from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.adapters.browsergym.source_qualification_authority import (
    SourceQualificationBrowserAuthority,
)
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.sites.worker_service import SiteService
from lab_generate_skill.bootstrap.admin_navigation_source_qualification import (
    qualify_admin_navigation_source,
    AdminNavigationSourceUnconfirmed,
)
from lab_generate_skill.bootstrap.source_browser_assets import SourceBrowserAssets
from lab_generate_skill.bootstrap.source_qualification_records import (
    SourceQualificationRecords,
)
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureRequest,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.browser_worker_acquisition import (
    BrowserWorkerAcquiredFact,
)
from lab_generate_skill.domain.evidence import EvidenceRequirements
from lab_generate_skill.domain.lifecycle import ResourceRecord
from lab_generate_skill.ports.contexts import ContextFactReads
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.adapters.storage.readonly_evidence import ReadOnlyEvidence
from lab_generate_skill.bootstrap.closed_source_read_bindings import (
    bind_closed_source_read,
)
from lab_generate_skill.bootstrap.admin_navigation_source_publication import (
    publish_admin_navigation_source,
)
import lab_generate_skill.bootstrap.admin_navigation_closed_source as closed_source
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from lab_generate_skill.domain.errors import OperationStopped, DispatchAlreadyCommitted
from lab_generate_skill.domain.site_resume import SiteResumeResult
from lab_generate_skill.sites.shopping_admin.frontend_recovery_contract import (
    AdminFrontendRecovered,
)
from lab_generate_skill.sites.shopping_admin.instance_contract import AdminInstancePlan
from lab_generate_skill.sites.shopping_admin.service_contract import (
    AdminServiceSpec,
    AdminPorts,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_lifecycle import (
    AdminNavigationLifecycle,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_recovery_contract import (
    NavigationRestored,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_state_policy import (
    navigation_initial_state_spec,
)
from lab_generate_skill.sites.shopping_admin.navigation_evidence_schema import (
    AdminNavigationPage,
)
from site_resource_fixtures import ResourceInstance, ResourceChannel
from site_worker_fixtures import sources
from browser_resource_fixtures import resource_case as browser_case
from browser_worker_fixtures import UnitBrowser
from browsergym_fixtures import CHROMIUM
from browser_worker_fixtures import LIBS
from generator_worker_fixtures import unit_guard
from frontend_fixtures import frontend
from frontend_recovery_fixtures import recovered_namespace
from admin_navigation_fixtures import Commands
from preparation_record_fixtures import put
from test_admin_navigation_input import contracts as contracts
from test_admin_navigation_source_authority import source_case
from test_admin_navigation_source_records import original_bytes, retain
from site_instance_fixtures import node_path as node_path
import lab_generate_skill.bootstrap.admin_navigation_source_qualification as module
import lab_generate_skill.bootstrap.source_qualification_measurement as measurement
import lab_generate_skill.adapters.browsergym.source_qualification_authority as browser_rights
import lab_generate_skill.adapters.browsergym.source_qualification_observation as observation_rights
import browser_resource_fixtures


def original_source_unit_case(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    fault: str,
    *,
    recovery_budgets: SourceRecoveryBudgets | None = None,
    use_publication_root: bool = False,
) -> Any:
    owner, c = source_case(tmp_path, node_path, monkeypatch, contracts)
    _, ref, public = contracts[0]
    raw = original_bytes()[ref.sha256]
    retain(c.evidence, raw, ref)
    spec = navigation_initial_state_spec(public.identity)
    recovery = RecoveryPlan(
        recovery_id="source-environment",
        owner=owner.scope.owner,
        baseline_ref=put(c.evidence, spec),
        restore_component_id="admin-frontend",
        restore_component_version="1",
        state_coverage=spec.environment_reset_checks,
    )
    token = c.spec.token.model_copy(update={"recovery_ref": put(c.evidence, recovery)})
    c.spec = c.spec.model_copy(
        update={
            "configuration": c.spec.configuration.model_copy(update={"token": token})
        }
    )
    c.op = c.op.model_copy(update={"recovery_ref": token.recovery_ref})
    root = (
        c.op.model_copy(
            update={
                "operation_id": "original-root",
                "allocation_id": None,
                "recovery_ref": None,
                "deadline": c.op.deadline + timedelta(seconds=120),
            }
        )
        if use_publication_root
        else None
    )
    published: list[Any] = []
    qualified: list[Any] = []
    browsers: list[Any] = []

    class UnitPhysical:
        def __init__(self, *args: Any, source: Any, **kwargs: Any) -> None:
            self.source = source

        def __enter__(self) -> "UnitPhysical":
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def __getattr__(self, name: str) -> Any:
            return getattr(self.source, name)

    class Native(ResourceInstance):
        def start(self, control: Any) -> Any:
            started = super().start(control)
            cfg = self.case.spec.configuration
            root = Path(cfg.files.node_root)
            (root / "state/app/var/training-mail").mkdir(parents=True)
            service = AdminServiceSpec(
                layout=AdminInstancePlan(
                    files=cfg.files, apptainer=cfg.apptainer
                ).layout,
                ports=AdminPorts(
                    web=12001,
                    database=12002,
                    redis=12003,
                    search=12004,
                    transport=12005,
                ),
            )
            self.native = AdminNavigationLifecycle(
                service, Commands(), lambda control: frontend(service)
            )
            return started

        def execute_task(self, request: Any, *, control: Any) -> Any:
            return self.native.execute_task(request, control=control)

        def resume_frontend(self, request: Any, *, control: Any) -> SiteResumeResult:
            control.checkpoint()
            assert self.native.restore_result is not None
            restored = NavigationRestored.model_validate_json(
                self.native.restore_result.private_result
            )
            result = AdminFrontendRecovered(
                stopped=restored.frontend,
                state_restored_sha256=hashlib.sha256(
                    restored.state.model_dump_json().encode()
                ).hexdigest(),
                before_start=restored.frontend.backend,
                namespaces=(
                    recovered_namespace("nginx-restored"),
                    recovered_namespace("php-restored"),
                ),
                backend_ready=True,
                frontend_ready=True,
            )
            return SiteResumeResult(
                request_sha256=request.digest, private_result=result.model_dump_json()
            )

    original_channel = ResourceChannel.__init__

    def channel(self: Any, case: Any) -> None:
        original_channel(self, case)
        self.engine = Native(case)
        self.service = SiteService(
            lambda configuration: self.engine, sources, unit_guard
        )

    class Page(UnitBrowser):
        def __init__(self, configuration: Any) -> None:
            super().__init__(configuration)
            self.last_capture: BrowserCaptureResult | None = None

        def capture_page(
            self, request: BrowserCaptureRequest, *, control: Any
        ) -> BrowserCaptureResult:
            control.checkpoint()
            assert self.last_readout is not None
            request.check_readout(self.spec, self.last_readout)
            self.last_capture = BrowserCaptureResult(
                request_sha256=request.digest,
                captured_at=datetime.now(timezone.utc),
                private_result=AdminNavigationPage(
                    url=self.last_readout.observation.tabs[0].url,
                    heading="Initial",
                    login=False,
                    page_error=False,
                ).model_dump_json(),
            )
            return self.last_capture

    class BrowserRights(SourceQualificationBrowserAuthority):
        def verify_closed(
            self,
            spec: Any,
            attempt: Any,
            ending: Any,
            step: Any,
            operation: Any,
            control: Any,
        ) -> Any:
            self.owner.require(operation, control, new_work=False)
            return browsers[0].authority.verify_closed(
                spec, attempt, ending, step, operation, control
            )

    def browser(spec: Any, operation: Any, **kwargs: Any) -> RetainedBrowserResource:
        root = tmp_path / "source-browser"
        root.mkdir()
        b = browser_case(
            root,
            monkeypatch,
            config=spec.configuration,
            store=c.evidence,
            declared_token=spec.token,
        )
        b.spec, b.op, b.journal = spec, operation, c.journal
        browsers.append(b)
        return RetainedBrowserResource(spec, operation, **kwargs)

    def kernel(*args: Any, **kwargs: Any) -> Any:
        b = browsers[0]
        record = b.journal.read(b.spec.token, b.op)
        fact = BrowserWorkerAcquiredFact.model_validate_json(
            b.evidence.read(record.events[2].evidence[0], b.controls.bind(b.op))
        )
        assert args[1] == fact.details.prepared.owner_guard.worker
        return SimpleNamespace(
            membership=fact.details.prepared.step.controller.target.worker
        )

    def before_publish(
        current: Any, facts: Any, operation: Any, *args: Any, **kwargs: Any
    ) -> Any:
        assert (
            current is owner
            and facts.baseline.status == "ready"
            and facts.reset.status == "safe"
        )
        assert facts.site_record.state == facts.browser_record.state == "closed"
        assert operation.deadline <= (root or c.op).deadline
        assert (
            facts.initial.preparation.prepared_ref == facts.baseline_inputs.prepared_ref
        )

        # Only the physical proof boundary is a declared unit premise. Original
        # preparation, native state, unique capture, Baseline/Reset/context joins
        # and compiled Admin closed reader execute their production predicates.
        def physical_record(value: Any, token: Any, evidence: Any, control: Any) -> Any:
            record = ResourceRecord.model_validate_json(__import__("json").dumps(value))
            assert record.token == token and [v.state for v in record.events] == [
                "registered",
                "acquiring",
                "acquired",
                "closing",
                "closed",
            ]
            intent = ResourceAcquisitionIntent.model_validate_json(
                evidence.read(record.events[1].evidence[0], control)
            )
            assert intent.token == token
            configuration = __import__("json").loads(
                evidence.read(intent.configuration_ref, control)
            )
            ending = __import__("json").loads(
                evidence.read(record.events[-1].evidence[0], control)
            )
            assert ending["token"] == token.model_dump(mode="json")
            return {"configuration": configuration, "ending": ending["details"]}

        monkeypatch.setattr(closed_source, "review_resource", physical_record)
        result = publish_admin_navigation_source(
            current,
            facts,
            operation,
            c.controls,
            source_reads=UnitRead(c.evidence, operation),
        )
        assert result.receipt.scope == owner.scope
        assert (
            result.contexts.load_context(result.material.context_ref, operation)
            == result.receipt
        )
        with pytest.raises(PermissionError):
            result.contexts.publish_context(result.receipt, operation)
        qualified.append(result)
        published.append(facts)
        raise PermissionError("Unit stop before actual Admin closed-source publication")

    # These are the same shared lifecycle injection points as Map; all Admin
    # binding/state/preparation/observation/capture/recovery codecs execute.
    monkeypatch.setattr(module, "ObservedSiteResourceAuthority", UnitPhysical)
    monkeypatch.setattr(ResourceChannel, "__init__", channel)
    monkeypatch.setattr(browser_resource_fixtures, "UnitBrowser", Page)
    monkeypatch.setattr(
        measurement, "SourceQualificationBrowserAuthority", BrowserRights
    )
    monkeypatch.setattr(measurement, "RetainedBrowserResource", browser)
    monkeypatch.setattr(browser_rights, "observe_process_cgroup", kernel)
    monkeypatch.setattr(observation_rights, "observe_process_cgroup", kernel)
    monkeypatch.setattr(module, "publish_admin_navigation_source", before_publish)
    parent = c.controls.bind(c.op)
    original_restore = getattr(module, "restore_source")

    def restore(*args: Any, **kwargs: Any) -> None:
        original_restore(*args, **kwargs)
        before = tuple(args[0].progress.references)
        with pytest.raises(DispatchAlreadyCommitted):
            original_restore(*args, **kwargs)
        assert tuple(args[0].progress.references) == before
        if fault == "cancel_after_reset":

            def stopped() -> float:
                raise OperationStopped("CANCELLED", c.op.operation_id)

            monkeypatch.setattr(parent, "checkpoint", stopped)
        if fault == "acquisition_expired_after_reset":

            def expired() -> float:
                raise OperationStopped("DEADLINE_EXCEEDED", c.op.operation_id)

            monkeypatch.setattr(parent, "checkpoint", expired)

    monkeypatch.setattr(module, "restore_source", restore)
    if fault == "restore_return_lost":
        original_request = SourceQualificationRecords.request

        def lost(records: Any, action: Any, operation: Any) -> Any:
            result = original_request(records, action, operation)
            if action == "restore":
                raise OSError("Original Admin restore return lost after persistence")
            return result

        monkeypatch.setattr(SourceQualificationRecords, "request", lost)

    class UnitRead(ClosedSourceReadTransport):
        def __init__(self, store: Any, operation: Any = None) -> None:
            self.store, self.operation = store, operation
            self.read_operation = (
                None
                if operation is None
                else operation.cleanup(
                    operation.operation_id + ".unit-admin-closed-read",
                    now=c.clock.utcnow(),
                    seconds=120,
                ).model_copy(update={"deadline": operation.deadline})
            )

        def require_current(self, material: Any, operation: Any) -> None:
            assert material.site.token.owner == owner.scope.owner
            assert material.site.slurm.execution == owner.execution
            assert material.site.slurm.parent == owner.controller
            assert operation.run_id == owner.scope.owner.run_id

        def check_current(self, control: Any) -> None:
            # This unit storage gate grants no actual Slurm/source/claim right.
            owner.require_caller(self.operation or c.op, control)
            control.checkpoint()

        def read(
            self,
            material: Any,
            control: Any,
            *,
            binding: Any = None,
            publication: Any = None,
            plan_inputs: Any = None,
            binding_reference: Any = None,
            execution_plan: Any = None,
            context_inputs: bool = False,
            actor_inputs: ActorAcquisitionInputs | None = None,
            preparation_read: PreparationReadRequest | None = None,
            baseline_read: BaselineReadRequest | None = None,
        ) -> Any:
            assert (
                baseline_read is None
            )  # This source fixture has no candidate-baseline role.
            assert (
                preparation_read is None
            )  # This unit transport has no preparation role.
            assert actor_inputs is None  # This unit reader cannot prove Actor bodies.
            assert self.operation is not None
            evidence = ReadOnlyEvidence(
                tmp_path / "evidence",
                max_object_bytes=64 * 1024**2,
                proposed=publication,
            )
            read = self.read_operation
            assert read is not None
            reader = bind_closed_source_read(material).contexts(
                evidence, c.controls, read
            )
            if context_inputs:
                assert isinstance(reader, ContextFactReads)
                result, inputs = reader.load_context_inputs(material.context_ref, read)
                self.last_reply = cast(Any, SimpleNamespace(context_inputs=inputs))
            else:
                result = reader.load_context(material.context_ref, read)
            if binding is not None:
                from lab_generate_skill.adapters.plans.qualified_binding_facts import (
                    require_qualified_binding_facts,
                )

                require_qualified_binding_facts(
                    material.context_ref,
                    reader,
                    evidence,
                    owner.scope.owner,
                    binding.binding,
                    binding.public_task,
                    binding.private_spec_json.encode(),
                    binding.baseline_json.encode(),
                    read,
                    control,
                )
            if binding_reference is not None:
                # Explicit synchronous unit transport; execute the same original
                # dependency and qualified-binding algorithms without claiming
                # installed process/storage evidence.
                from lab_generate_skill.adapters.plans.task_bindings import (
                    TaskBindingEvidenceReader,
                )
                from lab_generate_skill.adapters.plans.qualified_binding_facts import (
                    require_qualified_binding_facts,
                )

                from lab_generate_skill.adapters.plans.closed_source_protocol import (
                    ClosedSourceBindingBodies,
                )

                tasks = TaskBindingEvidenceReader(evidence)
                task = tasks.load(binding_reference, control)
                public, public_raw, private, baseline = tasks.dependencies_with_bodies(
                    task, control
                )
                require_qualified_binding_facts(
                    material.context_ref,
                    reader,
                    evidence,
                    owner.scope.owner,
                    task,
                    public,
                    private,
                    baseline,
                    read,
                    control,
                )
                self.last_reply = cast(
                    Any,
                    SimpleNamespace(
                        binding=task,
                        binding_reference=binding_reference,
                        binding_bodies=ClosedSourceBindingBodies(
                            binding=task,
                            public_task_json=public_raw.decode(),
                            private_spec_json=private.decode(),
                            baseline_json=baseline.decode(),
                        ),
                    ),
                )
            if execution_plan is not None:
                from lab_generate_skill.bootstrap.closed_map_source_read import (
                    read_execution_source_facts,
                )

                facts = read_execution_source_facts(
                    execution_plan,
                    material,
                    evidence,
                    c.controls,
                    reader,
                    read,
                    result,
                    control,
                )
                from lab_generate_skill.adapters.plans.claim_evidence import (
                    ClaimEvidence,
                )
                from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
                from lab_generate_skill.domain.claims import (
                    SourceClaimReceipt,
                    check_source_claim,
                )

                ref = facts.source.intent.binding.claim_ref
                record = ClaimEvidence(
                    evidence, EvidenceRunPlans(evidence, c.controls)
                ).load(ref, control)
                check_source_claim(record, ref, facts.source.run, facts.source.task)
                self.last_reply = cast(
                    Any,
                    SimpleNamespace(
                        execution_source=facts,
                        execution_claim=SourceClaimReceipt(
                            record=record, reference=ref
                        ),
                    ),
                )
            if plan_inputs is not None:
                # Explicit unit transport: run the exact full input checker;
                # this does not attest installed production transport/session.
                from lab_generate_skill.adapters.plans.evidence import (
                    check_run_plan_input_evidence,
                )

                check_run_plan_input_evidence(plan_inputs, evidence, control)
            return result

    assets = SourceBrowserAssets(
        CHROMIUM,
        CHROMIUM.rsplit("/", 3)[0],
        (LIBS,),
        0,
        10000,
        4096,
        EvidenceRequirements(events=("terminal",)),
    )
    with pytest.raises(AdminNavigationSourceUnconfirmed) as caught:
        qualify_admin_navigation_source(
            owner,
            c.spec,
            c.op,
            raw,
            ref,
            public,
            assets,
            journal=c.journal,
            controls=c.controls,
            clock=c.clock,
            prefix="admin-source-unit",
            metadata_seconds=120,
            source_reads=UnitRead(c.evidence),
            recovery_budgets=recovery_budgets,
            publication_root=root,
        )
    error = caught.value
    if error.primary is not None and not isinstance(
        error.primary, (PermissionError, OperationStopped)
    ):
        import traceback

        if error.primary is not None:
            traceback.print_exception(error.primary)
        for secondary in error.cleanup_errors:
            traceback.print_exception(secondary)
    assert error.progress.restore_attempted
    read = c.op.cleanup("admin-source-final-read", now=c.clock.utcnow(), seconds=30)
    assert c.journal.read(c.spec.token, read).state == "closed"
    assert not error.actual_actor_dispatched
    if fault == "restore_return_lost":
        assert not published and error.primary is None and error.progress.reset is None
        assert len(error.cleanup_errors) == 1 and isinstance(
            error.cleanup_errors[0], OSError
        )
    else:
        assert error.progress.reset is not None
        assert error.cleanup_errors == () and error.progress.reset.status == "safe"
        if fault in {"cancel_after_reset", "deadline_after_reset"}:
            assert not published and isinstance(error.primary, OperationStopped)
        else:
            assert len(published) == 1 and isinstance(error.primary, PermissionError)

    return SimpleNamespace(
        failure=error,
        owner=owner,
        site=c,
        qualified=qualified[0] if qualified else None,
        facts=published[0] if published else None,
        read_factory=UnitRead,
    )


@pytest.mark.parametrize("fault", ["none", "cancel_after_reset", "restore_return_lost"])
def test_admin_source_original_preparation_unique_capture_full_reset_and_partial_close(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    fault: str,
) -> None:
    original_source_unit_case(tmp_path, node_path, monkeypatch, contracts, fault)
