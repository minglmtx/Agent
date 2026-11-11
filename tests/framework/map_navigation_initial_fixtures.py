"""Original journal/wire/CAS/unique0 with explicit page/kernel/source doubles."""

from contextlib import contextmanager
from collections.abc import Iterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
import pytest
from lab_generate_skill.adapters.browsergym.resource import registered_browser
from lab_generate_skill.adapters.browsergym.prepared_authority import (
    PreparedBrowserAuthority,
)
from lab_generate_skill.adapters.browsergym.worker_service import BrowserService
from lab_generate_skill.adapters.browsergym.engine import BrowserGymEngine
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from lab_generate_skill.adapters.plans.prepared_browser import PreparedBrowserBinding
from lab_generate_skill.adapters.storage.initial_observations import (
    EvidenceInitialObservations,
)
from lab_generate_skill.bootstrap.browser_engine import build_browser_engine
from lab_generate_skill.bootstrap.map_overlay_records import map_prepared_browser_checks
from lab_generate_skill.bootstrap.map_initial_observation import (
    map_initial_observations,
)
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.map_navigation_browser_initialization import (
    MapNavigationInitialization,
)
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.map_initial_capture import MapInitialEvidence
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.sites.map.tasks.navigation_spec import NavigationSpec
from map_navigation_prepared_fixtures import NavigationPreparedCase
from map_navigation_browser_fixtures import Page, Clock
from map_registered_worker_fixtures import RegisteredMapCase
from map_qualification_fixtures import QualifiedMapCase
from browser_process_fixtures import case as synthetic_browser
from browser_resource_fixtures import resource_case, ResourceCase, ResourceChannel
from browser_worker_fixtures import configuration as base_configuration, sources
from generator_worker_fixtures import unit_guard
from browsergym_fixtures import LoopbackAuthority
from map_browser_capture_native import capture
from preparation_record_fixtures import put
from initial_observation_fixtures import Authority
from test_slurm_commands import guard
from map_navigation_browser_resource_fixtures import navigation_browser_resource


@dataclass
class NavigationInitialCase:
    browser: ResourceCase
    engine: BrowserGymEngine
    page: Page
    calls: list[str]
    session: EvidenceBrowserSession
    selection: InitialObservationSelection
    records: EvidenceInitialObservations
    evidence: MapInitialEvidence
    operation: OperationContext


@contextmanager
def initial_navigation(
    c: RegisteredMapCase,
    q: QualifiedMapCase,
    patch: pytest.MonkeyPatch,
    *,
    public_text: str | None = None,
    step_effect: Callable[[Page, str], None] | None = None,
) -> Iterator[NavigationInitialCase]:
    p = q.preparation
    assert isinstance(p, NavigationPreparedCase) and isinstance(
        c.private, NavigationSpec
    )
    c.observer = "controller"
    try:
        prepared = p.records.load(p.publication, p.request.operation)
        selected = MapNavigationInitialization(
            endpoint=q.live.site.instance.endpoint,
            prepared_ref=p.publication.prepared_ref,
            site_ref=put(c.resource.evidence, q.live.site),
            native_contract_sha256=c.private.native_contract_ref.sha256,
        )
        base = base_configuration(c.configuration.installation)
        cfg = BrowserWorkerConfiguration.model_validate(
            base.model_copy(
                update={
                    "spec": base.spec.model_copy(
                        update={"scope": c.scope, "task": prepared.public_task}
                    ),
                    "initialization": selected,
                }
            )
        )
        root = c.workspace / "navigation-browser"
        root.mkdir()
        backend = navigation_browser_resource(
            root,
            patch,
            configuration=cfg,
            store=c.resource.evidence,
            declared_token=q.plan.attempt_allocations[0],
            site=c.resource.spec,
            public_text=public_text,
            step_effect=step_effect,
        )
        b, engines, pages, calls = (
            backend.resource,
            backend.engines,
            backend.pages,
            backend.calls,
        )
        binding = PreparedBrowserBinding(
            p.publication,
            c.resource.spec,
            q.live.site,
            c.resource.op,
            evidence=c.resource.evidence,
            preparations=p.records,
            journal=c.resource.journal,
            task_checks=map_prepared_browser_checks(
                c.resource.evidence, c.configuration, q.live.site.instance
            ),
        )
        authority = PreparedBrowserAuthority(b.spec, binding, b.authority)
        with registered_browser(
            b.spec,
            b.op,
            journal=b.journal,
            evidence=b.evidence,
            controls=b.controls,
            clock=b.clock,
            authority=authority,
        ) as session:
            pair = capture(b, session, "map-navigation-initial")
            evidence = MapInitialEvidence(
                intent_ref=pair.intent_ref, result_ref=pair.result_ref
            )
            record = b.journal.read(b.spec.token, b.op)
            acquiring = ResourceAcquisitionIntent.model_validate_json(
                b.evidence.read(record.events[1].evidence[0])
            )
            assert session.resource_started_ref is not None
            selection = InitialObservationSelection(
                preparation=p.publication,
                browser_spec_ref=acquiring.configuration_ref,
                browser_acquired_ref=session.resource_started_ref,
            )
            records = map_initial_observations(
                b.evidence,
                b.controls,
                p.records,
                Authority(selection),
                evidence,
                initialization=cfg.initialization,
            )
            operation = p.request.operation.model_copy(
                update={"operation_id": "navigation-original-initial-checks"}
            )
            yield NavigationInitialCase(
                b,
                engines[0],
                pages[0],
                calls,
                session,
                selection,
                records,
                evidence,
                operation,
            )
    finally:
        c.observer = "worker"
