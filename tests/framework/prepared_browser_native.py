"""One registered browser inside the original registered Admin site lifetime."""

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import json
import pytest
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from lab_generate_skill.adapters.browsergym.prepared_authority import (
    PreparedBrowserAuthority,
)
from lab_generate_skill.adapters.plans.prepared_browser import PreparedBrowserBinding
from lab_generate_skill.domain.browser_initialization import (
    AdminProductInitialization,
    ShoppingOrderInitialization,
    BrowserInitialization,
)
from lab_generate_skill.domain.browser_session import BrowserSessionSpec, BrowserReadout
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.preparation_record import PreparedPublication
from lab_generate_skill.domain.site_resource import SiteResourceStarted
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.lifecycle import AllocationToken
from lab_generate_skill.ports.prepared_browser import PreparedBrowserTaskChecks
from collections.abc import Callable
from browser_resource_fixtures import resource_case, ResourceCase
from browser_worker_fixtures import configuration
from test_browser_resource_installed import EngineeringTreeAuthority
from site_preparation_native import NativePreparation
from test_slurm_commands import guard


def observe_prepared(
    native: NativePreparation,
    site: SiteResourceStarted,
    publication: PreparedPublication,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    declared_token: AllocationToken | None = None,
    on_initial: Callable[[ResourceCase, dict[str, Any]], None] | None = None,
    on_session: (
        Callable[[ResourceCase, EvidenceBrowserSession, dict[str, Any]], None] | None
    ) = None,
) -> dict[str, Any]:
    c = native.c
    assert native.request is not None
    prepared = native.records.load(
        publication,
        native.request.operation.cleanup(
            "browser-prepared-read", now=datetime.now(timezone.utc), seconds=30
        ),
    )
    base = configuration(c.spec.configuration.installation)
    session_spec = BrowserSessionSpec.model_validate(
        {
            **base.spec.model_dump(),
            "scope": prepared.scope,
            "task": prepared.public_task,
            "max_events": 4096,
        }
    )
    assert c.spec.configuration.site_id == prepared.public_task.identity.site
    selected: BrowserInitialization | None = None
    if c.spec.configuration.site_id == "reddit":
        from reddit_browser_native import initialization as reddit_initialization

        selected = reddit_initialization(native, site, publication)
    elif c.spec.configuration.site_id == "gitlab":
        from gitlab_browser_native import initialization

        selected = initialization(native, site, publication)
    elif c.spec.configuration.site_id != "map":
        initializer = (
            ShoppingOrderInitialization
            if c.spec.configuration.site_id == "shopping"
            else AdminProductInitialization
        )
        selected = initializer(
            endpoint=site.instance.endpoint,
            prepared_ref=publication.prepared_ref,
            site_ref=native.put(site),
        )
    declared_operation = None
    if c.spec.configuration.site_id == "map":
        from map_browser_native import declarations
        from map_preparation_native import MapPreparation

        if not isinstance(native, MapPreparation) or declared_token is None:
            raise ValueError("Selected Map preparation and declared browser required")
        config, declared_operation = declarations(
            native, site, publication, session_spec, base, root, declared_token
        )
    else:
        config = BrowserWorkerConfiguration.model_validate(
            {
                **base.model_dump(),
                "spec": session_spec,
                "initialization": selected,
            }
        )
    root.mkdir(mode=0o700)
    b = resource_case(
        root,
        monkeypatch,
        config=config,
        store=c.evidence,
        real_step=True,
        declared_token=declared_token,
    )
    b.op = declared_operation or b.op.model_copy(
        update={"deadline": datetime.now(timezone.utc) + timedelta(seconds=90)}
    )
    task_checks: PreparedBrowserTaskChecks | None = None
    if c.spec.configuration.site_id == "map":
        from lab_generate_skill.bootstrap.map_overlay_records import (
            map_prepared_browser_checks,
        )

        task_checks = map_prepared_browser_checks(
            c.evidence, c.spec.configuration, site.instance
        )
    if c.spec.configuration.site_id == "reddit":
        from lab_generate_skill.bootstrap.reddit_image_records import (
            reddit_prepared_browser_checks,
        )

        task_checks = reddit_prepared_browser_checks(c.evidence)
    if c.spec.configuration.site_id == "gitlab":
        from lab_generate_skill.bootstrap.gitlab_ssh_records import (
            gitlab_prepared_browser_checks,
        )
        from lab_generate_skill.bootstrap.gitlab_group_records import (
            group_prepared_browser_checks,
        )
        from lab_generate_skill.domain.gitlab_browser_initialization import (
            GitlabGroupInitialization,
            GitlabSshKeyInitialization,
        )

        if not isinstance(
            selected, (GitlabGroupInitialization, GitlabSshKeyInitialization)
        ):
            raise ValueError("Original explicit GitLab initializer required")
        checks_factory = (
            group_prepared_browser_checks
            if isinstance(selected, GitlabGroupInitialization)
            else gitlab_prepared_browser_checks
        )
        task_checks = checks_factory(c.evidence)
    binding = PreparedBrowserBinding(
        publication,
        c.spec,
        site,
        c.op,
        evidence=c.evidence,
        preparations=native.records,
        journal=c.journal,
        task_checks=task_checks,
    )
    authority = PreparedBrowserAuthority(
        b.spec, binding, EngineeringTreeAuthority(c.evidence)
    )
    with RetainedBrowserResource(
        b.spec,
        b.op,
        journal=b.journal,
        evidence=b.evidence,
        controls=b.controls,
        clock=b.clock,
        authority=authority,
    ) as session:
        assert (
            session.observation_ref is not None
            and session.last_return_ref is not None
            and session.resource_started_ref is not None
        )
        observation = Observation.model_validate_json(
            c.evidence.read(session.observation_ref, control=guard(10))
        )
        returned = BrowserReadout.model_validate_json(
            c.evidence.read(session.last_return_ref, control=guard(10))
        )
        assert returned.observation == observation and returned.action is None
        assert observation.sequence == 0 and observation.state == "ready"
        assert len(observation.tabs) == 1 and observation.text
        if c.spec.configuration.site_id == "shopping_admin":
            assert "Sony Headphones" in observation.text
            assert "Sign in" not in observation.text
        elif c.spec.configuration.site_id == "map":
            from lab_generate_skill.domain.map_browser_initialization import (
                MapNativeInitialization,
            )
            from lab_generate_skill.domain.map_navigation_browser_initialization import (
                MapNavigationInitialization,
            )
            from lab_generate_skill.sites.map.native_view_rules import original_document
            from lab_generate_skill.sites.map.navigation_initial_rules import (
                same_start_document,
            )

            if isinstance(config.initialization, MapNavigationInitialization):
                assert same_start_document(
                    prepared.public_task, observation.tabs[0].url
                )
            elif isinstance(config.initialization, MapNativeInitialization):
                assert original_document(prepared.public_task, observation.tabs[0].url)
            else:
                raise ValueError(
                    "Explicit original Map browser initialization required"
                )
        else:
            assert observation.tabs[0].url == prepared.public_task.start_url
        result = dict(
            initial_observation_ref=session.observation_ref.model_dump(mode="json"),
            initial_return_ref=session.last_return_ref.model_dump(mode="json"),
            browser_started_ref=session.resource_started_ref.model_dump(mode="json"),
            browser_spec=b.spec.model_dump(mode="json"),
            preparation_publication=publication.model_dump(mode="json"),
            environment_status="unknown",
            actor_authorized=False,
            complete_baseline=False,
        )
        if on_initial is not None:
            on_initial(b, result)
        if on_session is not None:
            on_session(b, session, result)
    closed = b.journal.read(
        b.spec.token,
        b.op.cleanup("browser-closed-read", now=datetime.now(timezone.utc), seconds=20),
    )
    assert closed.state == "closed"
    ending = json.loads(
        c.evidence.read(closed.events[-1].evidence[0], control=guard(10))
    )
    assert ending["details"]["cleanup_errors"] == []
    assert (
        c.journal.read(
            c.spec.token,
            c.op.cleanup(
                "site-still-acquired", now=datetime.now(timezone.utc), seconds=20
            ),
        ).state
        == "acquired"
    )
    result.update(
        browser_record=closed.model_dump(mode="json"),
        browser_ending=ending,
        original_browser_domain_closed_before_site_restore=True,
    )
    return result
