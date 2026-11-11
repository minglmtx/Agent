"""New registered worker uses original qualified URL; source/physical rights unit-only.

No original task, Actor, model, site service or database is executed. This
component combination does not qualify actual multi-candidate initial equality.
"""

import hashlib
from pathlib import Path
from urllib.parse import urlsplit
import pytest
from lab_generate_skill.adapters.sites.resource import registered_site
from lab_generate_skill.adapters.sites.task_site_authority import TaskSiteAuthority
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.site_resume import SiteResumeIntent
from lab_generate_skill.ports.lifecycle import OperationControl
from map_origin_fixtures import source_origin
from map_task_execution_current_fixtures import current_map_execution_case
from map_navigation_group_cases import SOURCES
from map_navigation_fixtures import navigation_case
from map_navigation_evaluation_fixtures import bind_original_contract
from map_registered_worker_fixtures import RegisteredMapCase
from site_resume_fixtures import Authority as ResumeAuthority, put
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard
from test_site_resource import inspect


def test_new_worker_exact_origin_context_rpc_restore_resume_and_original_close(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = node_path / "original-graph"
    source_root.mkdir()
    with current_map_execution_case(source_root, monkeypatch, SOURCES[0]) as source:
        spec, origin_authority = source_origin(source)
        old = source.p.original.resource
        assert isinstance(spec.configuration.map_inputs, MapNavigationWorkerInputs)
        policy = spec.configuration.map_inputs.origin
        # The source graph has its own historical source attempt. This new
        # worker belongs to the original pending construction candidate, never
        # an arbitrary replacement attempt. The synthetic setup dispatched no
        # candidate task/Actor; this is not actual multiattempt qualification.
        candidate_scope = source.p.original.scope
    assert inspect(old).state == "closed"
    # The historical graph above is explicitly synthetic, including its own
    # browser Reset. The current source worker is closed before fresh assembly.
    fresh = node_path / "fresh-candidate"
    fresh.mkdir()
    c = RegisteredMapCase(
        fresh,
        monkeypatch,
        navigation_source=SOURCES[0],
        origin=policy,
        task_scope=candidate_scope,
    )
    bind_original_contract(c)
    c.resource.op = c.resource.op.model_copy(
        update={"operation_id": "unit-fresh-origin-site-acquire"}
    )

    class UnitOnlyNativeSource:
        def __init__(self) -> None:
            self.actions: list[str] = []

        def verify_task(
            self,
            configuration: SiteWorkerConfiguration,
            request: SiteTaskRequest,
            control: OperationControl,
        ) -> None:
            control.checkpoint()
            assert configuration == c.configuration and request.task == c.scope.task
            assert request.action in ("snapshot", "prepare", "restore")
            self.actions.append(request.action)

    native = UnitOnlyNativeSource()
    authority = TaskSiteAuthority(
        c.resource.spec, c.resource.op, c.resource.authority, origin=origin_authority
    )
    try:
        with registered_site(
            c.resource.spec,
            c.resource.op,
            journal=c.resource.journal,
            evidence=c.resource.evidence,
            controls=c.resource.controls,
            clock=c.resource.clock,
            authority=authority,
        ) as live:
            assert c.worker is not None
            authority.bind_native(native, live.site)
            assert c.worker.instance.expected_web_port == policy.requested_web_port
            assert live.site.instance.endpoint == c.case.spec.endpoint
            assert (
                policy.source_start_url == navigation_case(SOURCES[0]).public.start_url
            )
            assert (
                urlsplit(live.site.instance.endpoint).netloc
                == urlsplit(policy.source_start_url).netloc
            )
            original_lease = c.worker.instance.lease
            snapshot = live.tasks.execute_task(c.request("snapshot"), control=guard())
            c.snapshot_ref = c.put(
                snapshot.private_result.encode(), "map-navigation-snapshot/1"
            )
            live.tasks.execute_task(c.request("prepare"), control=guard())
            restored = live.tasks.execute_task(c.request("restore"), control=guard())
            request = c.resume_request(restored)
            intent = put(
                c.resource.evidence,
                SiteResumeIntent(
                    configuration_sha256=hashlib.sha256(
                        c.configuration.model_dump_json().encode()
                    ).hexdigest(),
                    request=request,
                ),
            )
            live.resume.resume_frontend(
                request, intent, ResumeAuthority(c.resource.evidence), control=guard()
            )
            assert c.worker.instance.lease is original_lease
            assert c.worker.tasks is not None and c.worker.tasks.phase == "resumed"
        assert inspect(c.resource).state == "closed" and c.worker.closed
        assert c.case.ports.lease.releases == 0
        assert native.actions == ["snapshot", "prepare", "restore"]
    finally:
        c.close_sockets()
