"""Real record/journal composition with synthetic workers and explicit test policy."""

from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
import pytest
from lab_generate_skill.adapters.sites.resource import registered_site
from lab_generate_skill.adapters.plans.prepared_browser import PreparedBrowserBinding
from lab_generate_skill.adapters.browsergym.prepared_authority import (
    PreparedBrowserAuthority,
)
from lab_generate_skill.domain.browser_initialization import AdminProductInitialization
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from site_resource_fixtures import Case as SiteCase, resource_case as site_case
from site_worker_fixtures import configuration as site_configuration
from browser_resource_fixtures import ResourceCase, resource_case as browser_case
from browser_worker_fixtures import configuration
from preparation_record_fixtures import Case as PreparationCase, fixture, put
from test_admin_description_inputs import FIXTURE
import json


@dataclass
class Case:
    site: SiteCase
    preparation: PreparationCase
    browser: ResourceCase
    binding: PreparedBrowserBinding
    authority: PreparedBrowserAuthority


@contextmanager
def prepared_case(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    initial_checks: tuple[str, ...] = ("initial",),
) -> Iterator[Case]:
    for name in ("site", "preparation", "browser"):
        (root / name).mkdir()
    site_config = site_configuration(job_id="4752096")
    site_config = site_config.model_copy(
        update={
            "token": site_config.token.model_copy(
                update={"expected_resource_id": "test-instance"}
            ),
            "files": site_config.files.model_copy(
                update={"instance_id": "test-instance"}
            ),
        }
    )
    s = site_case(root / "site", monkeypatch, config=site_config)
    with registered_site(
        s.spec,
        s.op,
        journal=s.journal,
        evidence=s.evidence,
        controls=s.controls,
        clock=s.clock,
        authority=s.authority,
    ) as live:
        endpoint = live.site.instance.endpoint
        p = fixture(
            root / "preparation",
            store=s.evidence,
            site_token=s.spec.token,
            start_url=endpoint + json.loads(FIXTURE.read_bytes())["start_path"],
            initial_checks=initial_checks,
        )
        publication = p.adapter.publish(p.selection, p.request.operation)
        prepared = p.adapter.load(publication, p.request.operation)
        base = configuration(s.spec.configuration.installation)
        spec = BrowserSessionSpec.model_validate(
            {
                **base.spec.model_dump(),
                "scope": prepared.scope,
                "task": prepared.public_task,
            }
        )
        config = BrowserWorkerConfiguration.model_validate(
            {
                **base.model_dump(),
                "spec": spec,
                "initialization": AdminProductInitialization(
                    endpoint=endpoint,
                    prepared_ref=publication.prepared_ref,
                    site_ref=put(s.evidence, live.site),
                ),
            }
        )
        b = browser_case(root / "browser", monkeypatch, config=config, store=s.evidence)
        binding = PreparedBrowserBinding(
            publication,
            s.spec,
            live.site,
            s.op,
            evidence=s.evidence,
            preparations=p.adapter,
            journal=s.journal,
        )
        authority = PreparedBrowserAuthority(b.spec, binding, b.authority)
        yield Case(s, p, b, binding, authority)
