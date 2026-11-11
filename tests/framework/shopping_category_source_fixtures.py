"""Production source composition with explicit synthetic native/page/kernel facts."""

from datetime import datetime, timezone
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
from lab_generate_skill.adapters.storage.readonly_evidence import ReadOnlyEvidence
from lab_generate_skill.adapters.sites.worker_service import SiteService
from lab_generate_skill.bootstrap.closed_source_read_bindings import (
    bind_closed_source_read,
)
from lab_generate_skill.bootstrap.shopping_category_source_publication import (
    publish_category_navigation_source,
)
from lab_generate_skill.bootstrap.shopping_category_source_qualification import (
    qualify_category_navigation_source,
)
from lab_generate_skill.bootstrap.shopping_category_site_configuration import (
    shopping_category_site_configuration,
)
from lab_generate_skill.bootstrap.shopping_category_navigation import (
    load_category_navigation_inputs,
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
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRequirements
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.contexts import ContextFactReads
from lab_generate_skill.sites.shopping.tasks.navigation_policy import (
    category_navigation_initial_spec,
)
from lab_generate_skill.sites.shopping.navigation_page_capture import (
    ShoppingCategoryPageCollector,
)
from lab_generate_skill.sites.shopping.worker_instance import ShoppingWorkerInstance
from lab_generate_skill.sites.shopping.tasks.order_eta_native import SHOPPING_IMAGE_SHA
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from shopping_category_browser_fixtures import Page as CategoryPage
from shopping_category_source_raw_fixtures import complete_unit_closed_raw
from shopping_services_fixtures import Group, plan as files_plan
from shopping_task_fixtures import case as native_case
from test_shopping_category_source_records import source_case
from test_shopping_category_navigation_input import reference
from site_resource_fixtures import ResourceInstance, ResourceChannel
from site_worker_fixtures import sources
from browser_resource_fixtures import resource_case as browser_case
from browser_worker_fixtures import UnitBrowser, LIBS
from browsergym_fixtures import CHROMIUM
from generator_worker_fixtures import unit_guard
from preparation_record_fixtures import put
import lab_generate_skill.bootstrap.shopping_category_source_qualification as module
import lab_generate_skill.bootstrap.source_qualification_measurement as measurement
import lab_generate_skill.adapters.browsergym.source_qualification_authority as browser_rights
import lab_generate_skill.adapters.browsergym.source_qualification_observation as observation_rights
import browser_resource_fixtures


def source_unit_case(
    root: Path,
    node: Path,
    patch: pytest.MonkeyPatch,
    original: Any,
    fault: str,
    *,
    installation: ReleaseInstallation | None = None,
) -> Any:
    raw, _, public = original
    owner, c = source_case(root, node, patch, public, raw)
    installation = (
        c.spec.configuration.installation
        if installation is None
        else ReleaseInstallation.model_validate(installation)
    )
    native_root = node / "source-native"
    native_root.mkdir()
    files = files_plan(native_root / "instance")
    files = files.model_copy(
        update={
            "workspace_root": installation.workspace_root,
            "source_path": installation.workspace_root + "/" + files.image.path,
            "image": files.image.model_copy(update={"sha256": SHOPPING_IMAGE_SHA}),
        }
    )
    policy = category_navigation_initial_spec(public.identity)
    recovery = RecoveryPlan(
        recovery_id="source-environment",
        owner=owner.scope.owner,
        baseline_ref=put(c.evidence, policy),
        restore_component_id="shopping-services",
        restore_component_version="1",
        state_coverage=policy.environment_reset_checks,
    )
    token = c.spec.token.model_copy(
        update={
            "expected_resource_id": files.instance_id,
            "recovery_ref": put(c.evidence, recovery),
        }
    )
    selected = c.spec.configuration.shopping_category_inputs
    assert selected is not None
    configuration = shopping_category_site_configuration(
        load_category_navigation_inputs(raw, reference(raw), public).private_spec,
        owner.scope,
        token,
        files,
        installation,
        selected.origin,
    )
    c.spec = c.spec.model_copy(update={"configuration": configuration})
    c.op = c.op.model_copy(update={"recovery_ref": token.recovery_ref})
    ref = reference(raw)
    c.evidence.put(
        raw,
        EvidenceMetadata.model_validate(
            ref.model_dump(
                include={"media_type", "content_schema", "visibility", "producer"}
            )
        ),
    )
    browsers: list[Any] = []
    publications: list[Any] = []

    host, pin = current_process_identity(), Group.pin_namespace

    def original_host(
        group: Group, name: str, control: OperationControl
    ) -> NativeNamespaceIdentity:
        value = pin(group, name, control)
        value = value.model_copy(
            update={
                "launcher": value.launcher.model_copy(
                    update={
                        "node_id": host.node_id,
                        "boot_id": host.boot_id,
                        "start_ticks": host.start_ticks + 10 + group.generation,
                    }
                ),
                "init": value.init.model_copy(
                    update={
                        "node_id": host.node_id,
                        "boot_id": host.boot_id,
                        "start_ticks": host.start_ticks + 20 + group.generation,
                    }
                ),
            }
        )
        group.pins[-1] = value
        return value

    patch.setattr(Group, "pin_namespace", original_host)

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
            original, _, _ = native_case(
                native_root, declared_files=self.case.spec.configuration.files
            )

            def forbidden_customer(value: Any) -> str:
                raise AssertionError(
                    "Category source cannot use ETA customer initialization"
                )

            self.native = ShoppingWorkerInstance(original.instance, forbidden_customer)
            assert self.native.instance.files_plan == self.case.spec.configuration.files
            return started

        def execute_task(self, request: Any, *, control: Any) -> Any:
            return self.native.execute_task(request, control=control)

        def resume_frontend(self, request: Any, *, control: Any) -> Any:
            return self.native.resume_frontend(request, control=control)

        def stop(self, control: Any) -> Any:
            self.native.stop(control)
            return super().stop(control)

    original_channel = ResourceChannel.__init__

    def channel(current: Any, case: Any) -> None:
        original_channel(current, case)
        current.engine = Native(case)
        current.service = SiteService(
            lambda config: current.engine, sources, unit_guard
        )

    class Page(UnitBrowser):
        def __init__(self, configuration: Any) -> None:
            super().__init__(configuration)
            self.last_capture: BrowserCaptureResult | None = None

        def capture_page(
            self, request: BrowserCaptureRequest, *, control: Any
        ) -> BrowserCaptureResult:
            control.checkpoint()
            if fault == "capture":
                raise PermissionError("Explicit category initial-capture cancellation")
            assert self.last_readout is not None
            request.check_readout(self.spec, self.last_readout)
            page = CategoryPage(self.spec.task)
            page.url = self.spec.task.start_url
            self.last_capture = BrowserCaptureResult(
                request_sha256=request.digest,
                captured_at=datetime.now(timezone.utc),
                private_result=ShoppingCategoryPageCollector().collect(
                    page, request.collector_id, request.collector_version, control
                ),
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
        current_root = root / "source-browser"
        current_root.mkdir()
        b = browser_case(
            current_root,
            patch,
            config=spec.configuration,
            store=c.evidence,
            declared_token=spec.token,
        )
        b.spec, b.op, b.journal = spec, operation, c.journal
        browsers.append(b)
        complete_unit_closed_raw(patch)
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

    class UnitRead(ClosedSourceReadTransport):
        def __init__(self) -> None:
            self.store = cast(Any, c.evidence)
            self.operation: Any = None
            self.read_operation: Any = None

        def require_current(self, material: Any, operation: Any) -> None:
            assert material.site.token.owner == owner.scope.owner
            assert material.site.slurm.execution == owner.execution
            assert material.site.slurm.parent == owner.controller
            if self.operation != operation:
                self.read_operation = operation.cleanup(
                    operation.operation_id + ".unit-source-read",
                    now=c.clock.utcnow(),
                    seconds=120,
                )
                self.operation = operation

        def check_current(self, control: OperationControl) -> None:
            # Live source gates precede the later closed-source publication.
            # Both phases retain the fixture's explicit original caller premise.
            current = c.op if self.operation is None else self.operation
            owner.require(current, control, new_work=False)

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
            **additional_reads: Any,
        ) -> Any:
            assert self.operation is not None
            assert binding is plan_inputs is binding_reference is execution_plan is None
            evidence = ReadOnlyEvidence(
                root / "evidence", max_object_bytes=64 * 1024**2, proposed=publication
            )
            read = self.read_operation
            assert read is not None
            contexts = bind_closed_source_read(material).contexts(
                evidence, c.controls, read
            )
            assert not set(additional_reads) - {"context_inputs"}
            if additional_reads.get("context_inputs", False):
                assert isinstance(contexts, ContextFactReads)
                result, inputs = contexts.load_context_inputs(
                    material.context_ref, read
                )
                self.last_reply = cast(Any, SimpleNamespace(context_inputs=inputs))
                return result
            return contexts.load_context(material.context_ref, read)

    def publish(
        current: Any, facts: Any, operation: Any, controls: Any, *, source_reads: Any
    ) -> Any:
        assert facts.baseline.status == "ready" and facts.reset.status == "safe"
        assert facts.site_record.state == facts.browser_record.state == "closed"
        value = publish_category_navigation_source(
            current, facts, operation, controls, source_reads=source_reads
        )
        publications.append(value)
        return value

    patch.setattr(module, "ObservedSiteResourceAuthority", UnitPhysical)
    patch.setattr(ResourceChannel, "__init__", channel)
    patch.setattr(browser_resource_fixtures, "UnitBrowser", Page)
    patch.setattr(measurement, "SourceQualificationBrowserAuthority", BrowserRights)
    patch.setattr(measurement, "RetainedBrowserResource", browser)
    patch.setattr(browser_rights, "observe_process_cgroup", kernel)
    patch.setattr(observation_rights, "observe_process_cgroup", kernel)
    patch.setattr(module, "publish_category_navigation_source", publish)
    if fault == "restore-return-lost":
        original_request = SourceQualificationRecords.request

        def lost(records: Any, action: Any, operation: Any) -> Any:
            value = original_request(records, action, operation)
            if action == "restore":
                raise OSError(
                    "Original category restore returned after persistence; acknowledgement lost"
                )
            return value

        patch.setattr(SourceQualificationRecords, "request", lost)
    if fault == "cancel-after-reset":
        original_restore = getattr(module, "restore_source")
        parent = c.controls.bind(c.op)

        def restore(*args: Any, **kwargs: Any) -> None:
            original_restore(*args, **kwargs)

            def cancelled() -> float:
                raise OperationStopped("CANCELLED", c.op.operation_id)

            patch.setattr(parent, "checkpoint", cancelled)

        patch.setattr(module, "restore_source", restore)
    assets = SourceBrowserAssets(
        CHROMIUM,
        CHROMIUM.rsplit("/", 3)[0],
        (LIBS,),
        0,
        10000,
        4096,
        EvidenceRequirements(events=("terminal",)),
    )

    def run() -> Any:
        return qualify_category_navigation_source(
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
            prefix="category-source-unit",
            metadata_seconds=120,
            source_reads=UnitRead(),
        )

    return SimpleNamespace(
        run=run,
        site=c,
        owner=owner,
        publications=publications,
        browsers=browsers,
        assets=assets,
    )
