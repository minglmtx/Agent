"""One real CAS/journal graph and fixed Map browser assembly with explicit doubles."""

import pytest
from lab_generate_skill.adapters.plans.prepared_browser import PreparedBrowserBinding
from lab_generate_skill.adapters.browsergym.prepared_authority import (
    PreparedBrowserAuthority,
)
from lab_generate_skill.bootstrap.map_overlay_records import map_prepared_browser_checks
from lab_generate_skill.domain.map_browser_initialization import MapNativeInitialization
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.adapters.sites.resource import RegisteredSite
from map_browser_collection_fixtures import CollectionCase
from map_registered_worker_fixtures import RegisteredMapCase
from map_prepared_records_fixtures import PreparedMapCase
from map_browser_initialization_fixtures import public_task
from preparation_record_fixtures import put


def bind(
    c: RegisteredMapCase,
    p: PreparedMapCase,
    live: RegisteredSite,
    patch: pytest.MonkeyPatch,
    *,
    browser: CollectionCase | None = None,
) -> tuple[CollectionCase, PreparedBrowserBinding, PreparedBrowserAuthority]:
    if browser is None:
        root = c.workspace / "browser"
        root.mkdir(mode=0o700)
        browser = CollectionCase(
            root,
            patch,
            owner=c.scope.owner,
            store=c.resource.evidence,
            workspace=c.workspace,
        )
    b = browser
    endpoint = live.site.instance.endpoint
    cfg = b.configuration
    b.configuration = BrowserWorkerConfiguration.model_validate(
        cfg.model_copy(
            update={
                "spec": cfg.spec.model_copy(
                    update={"scope": c.scope, "task": public_task(endpoint)}
                ),
                "installation": c.configuration.installation,
                "initialization": MapNativeInitialization(
                    endpoint=endpoint,
                    prepared_ref=p.publication.prepared_ref,
                    site_ref=put(c.resource.evidence, live.site),
                ),
            }
        )
    )
    b.resource.spec = BrowserResourceSpec.model_validate(
        b.resource.spec.model_copy(
            update={
                "configuration": b.configuration,
                "slurm": b.resource.spec.slurm.model_copy(
                    update={
                        "execution": c.resource.spec.slurm.execution,
                        "parent": c.resource.spec.slurm.parent,
                    }
                ),
            }
        )
    )
    binding = PreparedBrowserBinding(
        p.publication,
        c.resource.spec,
        live.site,
        c.resource.op,
        evidence=c.resource.evidence,
        preparations=p.records,
        journal=c.resource.journal,
        task_checks=map_prepared_browser_checks(
            c.resource.evidence, c.configuration, live.site.instance
        ),
    )
    return (
        b,
        binding,
        PreparedBrowserAuthority(b.resource.spec, binding, b.resource.authority),
    )
