"""Group source composition with explicit SQL/services/page/kernel doubles.

Uses the real current Slurm caller and original record/lifecycle predicates.
The unit reader cannot grant actual source/Actor/claim or training permission.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
import hashlib
import pytest
from lab_generate_skill.domain.actor_acquisition_inputs import ActorAcquisitionInputs
from lab_generate_skill.domain.preparation_read import PreparationReadRequest
from lab_generate_skill.domain.baseline_read import BaselineReadRequest
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
from lab_generate_skill.adapters.storage.readonly_evidence import ReadOnlyEvidence
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_current_cgroup
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.bootstrap.gitlab_group_source_qualification import (
    qualify_group_source,
    GroupSourceUnconfirmed,
)
from lab_generate_skill.bootstrap.gitlab_group_source_publication import (
    publish_group_source,
)
from lab_generate_skill.bootstrap.gitlab_group_source import GroupSourceSelection
from lab_generate_skill.bootstrap.source_browser_assets import SourceBrowserAssets
from lab_generate_skill.bootstrap.source_qualification_records import (
    SourceQualificationRecords,
)
from lab_generate_skill.bootstrap.closed_source_read_bindings import (
    bind_closed_source_read,
)
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureRequest,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.browser_worker_acquisition import (
    BrowserWorkerAcquiredFact,
)
from lab_generate_skill.domain.evidence import EvidenceRequirements, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.lifecycle import ResourceRecord, RecoveryPlan
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.native_private_json import GITLAB_GROUP_PRIVATE_JSON
from lab_generate_skill.domain.errors import OperationStopped, DispatchAlreadyCommitted
from lab_generate_skill.domain.source_recovery_budget import SourceRecoveryBudgets
from lab_generate_skill.domain.gitlab_group_origin import (
    GitlabGroupOrigin,
    GitlabGroupWorkerInputs,
)
from lab_generate_skill.domain.site_resume import SiteResumeResult
from lab_generate_skill.sites.gitlab.tasks.group_policy import group_initial_spec
from lab_generate_skill.sites.gitlab.tasks.group_resume import GroupResume
from lab_generate_skill.sites.gitlab.evidence_schema import GitlabPageHealth
from lab_generate_skill.sites.gitlab.image import GITLAB_IMAGE_SHA
from site_resource_fixtures import (
    ResourceInstance,
    ResourceChannel,
    resource_case,
    Case,
)
from site_worker_fixtures import sources
from browser_resource_fixtures import resource_case as browser_case
from browser_worker_fixtures import UnitBrowser, LIBS
from browsergym_fixtures import CHROMIUM
from generator_worker_fixtures import unit_guard
from preparation_record_fixtures import put
from gitlab_group_lifecycle_fixtures import case as group_native_case
from gitlab_site_storage_live import missing_asset_configuration
from storage_installation_fixtures import storage_installation
from test_linux_cgroups import actual_slurm_execution
from test_slurm_commands import guard
import lab_generate_skill.bootstrap.gitlab_group_source_qualification as module
import lab_generate_skill.bootstrap.gitlab_group_closed_source as closed_source
import lab_generate_skill.bootstrap.source_qualification_measurement as measurement
import lab_generate_skill.adapters.browsergym.source_qualification_authority as browser_rights
import lab_generate_skill.adapters.browsergym.source_qualification_observation as observation_rights
import browser_resource_fixtures


def original_bytes() -> dict[str, bytes]:
    from test_gitlab_group_complete_starts import original, PINS

    return {sha: original(source)[0] for source, sha in PINS.items()}


def retain(store: Any, raw: bytes, ref: Any) -> None:
    meta = EvidenceMetadata.model_validate(
        ref.model_dump(
            include={"media_type", "content_schema", "visibility", "producer"}
        )
    )
    assert store.put(raw, meta) == ref


def source_case(
    root: Path,
    node: Path,
    patch: pytest.MonkeyPatch,
    contracts: Any,
    *,
    attempt_id: str = "source-only-group",
    explicit_origin: bool = False,
) -> tuple[OriginalSourceQualificationOwner, Case]:
    execution, _ = actual_slurm_execution()
    controller = observe_current_cgroup(
        execution, current_process_identity(), guard(30)
    ).membership
    cfg = missing_asset_configuration(
        storage_installation(),
        job_id=execution.job_id,
        root=root,
        parent=node / "primitive",
    )
    Path(cfg.files.node_root).parent.mkdir(parents=True, exist_ok=True)
    assert cfg.private_evidence is not None
    cfg = SiteWorkerConfiguration.model_validate(
        cfg.model_copy(
            update={
                "private_evidence": cfg.private_evidence.model_copy(
                    update={"profile": GITLAB_GROUP_PRIVATE_JSON}
                ),
                "files": cfg.files.model_copy(
                    update={
                        "image": cfg.files.image.model_copy(
                            update={
                                "sha256": GITLAB_IMAGE_SHA,
                                "size_bytes": 22167199744,
                            }
                        )
                    }
                ),
            }
        )
    )
    c = resource_case(root, patch, config=cfg)
    c.spec = SiteResourceSpec.model_validate(
        c.spec.model_copy(
            update={
                "slurm": c.spec.slurm.model_copy(
                    update={"execution": execution, "parent": controller}
                )
            }
        )
    )
    public = contracts[0][2]
    scope = StateScope(
        owner=cfg.token.owner,
        task=public.identity,
        attempt_id=attempt_id,
        context_id=(
            "source-context"
            if attempt_id == "source-only-group"
            else "source-context-" + attempt_id
        ),
    )
    if explicit_origin:
        from urllib.parse import urlsplit

        _, ref, public = contracts[0]
        selection = GroupSourceSelection(original_bytes()[ref.sha256], public)
        private = selection.load(ref, public)
        declared = GitlabGroupWorkerInputs(
            scope=scope,
            native_contract_sha256=ref.sha256,
            private_input_sha256=hashlib.sha256(
                private.model_dump_json().encode()
            ).hexdigest(),
            origin=GitlabGroupOrigin(
                endpoint=f"http://127.0.0.1:{urlsplit(public.start_url).port}/"
            ),
        )
        cfg = SiteWorkerConfiguration.model_validate(
            c.spec.configuration.model_copy(
                update={
                    "schema_version": "site-worker-configuration/8",
                    "gitlab_group_inputs": declared,
                }
            )
        )
        c.spec = SiteResourceSpec.model_validate(
            c.spec.model_copy(update={"configuration": cfg})
        )
    return OriginalSourceQualificationOwner(scope, execution, controller, c.evidence), c


def group_source_unit_case(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    fault: str,
    *,
    attempt_id: str = "source-only-group",
    recovery_budgets: SourceRecoveryBudgets | None = None,
    use_publication_root: bool = False,
    explicit_origin: bool = False,
) -> Any:
    owner, c = source_case(
        tmp_path,
        node_path,
        monkeypatch,
        contracts,
        attempt_id=attempt_id,
        explicit_origin=explicit_origin,
    )
    _, ref, public = contracts[0]
    raw = original_bytes()[ref.sha256]
    retain(c.evidence, raw, ref)
    spec = group_initial_spec(public.identity)
    recovery = RecoveryPlan(
        recovery_id="source-environment",
        owner=owner.scope.owner,
        baseline_ref=put(c.evidence, spec),
        restore_component_id="gitlab-services",
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
            super().start(control)
            cfg = self.case.spec.configuration
            self.primitive = group_native_case(
                Path(cfg.files.node_root).parent,
                configured=cfg,
                owner_guard=unit_guard(current_process_identity(), control),
            )
            self.primitive.artifacts.store = c.evidence
            return self.primitive.artifacts.context.instance

        def execute_task(self, request: Any, *, control: Any) -> Any:
            return self.primitive.task.execute_task(request, control=control)

        def resume_frontend(self, request: Any, *, control: Any) -> SiteResumeResult:
            return GroupResume(self.primitive.task).resume_frontend(
                request, control=control
            )

        def stop(self, control: Any) -> Any:
            super().stop(control)
            return self.primitive.task.instance.stop(control)

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
                private_result=GitlabPageHealth(
                    url=self.last_readout.observation.tabs[0].url,
                    title="Original Group initial document",
                    http_status=200,
                    status_source="navigation_timing",
                    login_page=False,
                    error_page=False,
                    account_id=1,
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
        if recovery_budgets is not None:
            assert kwargs["cleanup_seconds"] == recovery_budgets.browser_close_seconds
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
        # and compiled Group closed reader execute their production predicates.
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
        result = publish_group_source(
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
        raise PermissionError("Unit stop before actual Group closed-source publication")

    # These are the same shared lifecycle injection points as Map; all Group
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
    monkeypatch.setattr(module, "publish_group_source", before_publish)
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
                raise OSError("Original Group restore return lost after persistence")
            return result

        monkeypatch.setattr(SourceQualificationRecords, "request", lost)

    class UnitRead(ClosedSourceReadTransport):
        def __init__(self, store: Any, operation: Any = None) -> None:
            self.store, self.operation = store, operation
            self.read_operation = (
                None
                if operation is None
                else operation.cleanup(
                    operation.operation_id + ".unit-group-closed-read",
                    now=c.clock.utcnow(),
                    seconds=120,
                )
            )

        def require_current(self, material: Any, operation: Any) -> None:
            assert material.site.token.owner == owner.scope.owner
            assert material.site.slurm.execution == owner.execution
            assert material.site.slurm.parent == owner.controller
            assert operation.run_id == owner.scope.owner.run_id

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
            )  # Group source publication is not candidate baseline IO.
            assert (
                preparation_read is None
            )  # This unit transport has no preparation role.
            assert actor_inputs is None  # This unit reader cannot prove Actor bodies.
            assert not context_inputs  # Source-publication-only unit transport.
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

                claim_ref = facts.source.intent.binding.claim_ref
                claim_record = ClaimEvidence(
                    evidence, EvidenceRunPlans(evidence, c.controls)
                ).load(claim_ref, control)
                check_source_claim(
                    claim_record, claim_ref, facts.source.run, facts.source.task
                )
                self.last_reply = cast(
                    Any,
                    SimpleNamespace(
                        execution_source=facts,
                        execution_claim=SourceClaimReceipt(
                            record=claim_record, reference=claim_ref
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
    with pytest.raises(GroupSourceUnconfirmed) as caught:
        qualify_group_source(
            owner,
            c.spec,
            c.op,
            GroupSourceSelection(raw, public),
            ref,
            assets,
            journal=c.journal,
            controls=c.controls,
            clock=c.clock,
            prefix="group-source-unit",
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
    read = c.op.cleanup("group-source-final-read", now=c.clock.utcnow(), seconds=30)
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
