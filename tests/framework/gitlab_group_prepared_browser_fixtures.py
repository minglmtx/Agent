"""Group current record graph; services/kernel/environment are explicit doubles."""

from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
import hashlib, json
import pytest
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.sites.gitlab.image import GITLAB_IMAGE_SHA
from gitlab_group_qualification_fixtures import QualifiedCase, qualify_existing
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteSlurmBinding,
    SiteResourceReady,
    SiteResourceStarted,
)
from lab_generate_skill.domain.site_worker import SiteWorkerReady
from lab_generate_skill.domain.slurm_step import SlurmStepTarget, SlurmControllerStep
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.bootstrap.gitlab_group_browser_declarations import (
    group_browser_declaration,
)
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.adapters.ledger.resource_journal import FileResourceJournal
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.adapters.plans.prepared_browser import PreparedBrowserBinding
from lab_generate_skill.adapters.browsergym.prepared_authority import (
    PreparedBrowserAuthority,
)
from lab_generate_skill.bootstrap.gitlab_group_records import (
    group_prepared_browser_checks,
)
from gitlab_group_preparation_fixtures import (
    Case as PreparationCase,
    prepared_case,
    put,
    metadata,
)
from browser_step_fixtures import binding
from browser_resource_fixtures import ResourceCase, resource_case
from browser_worker_fixtures import configuration
from site_worker_fixtures import sources
from test_resource_journal import context, NoCancellation
from test_slurm_commands import guard
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)


@dataclass
class Case:
    preparation: PreparationCase
    browser: ResourceCase
    binding: PreparedBrowserBinding
    authority: PreparedBrowserAuthority
    qualified: QualifiedCase


@contextmanager
def joined(root: Path, node: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Case]:
    controller = current_process_identity()
    native_guard = ProcessOwnerGuard(
        controller=controller,
        supervisor=controller.model_copy(
            update={"process_id": controller.process_id + 20000000}
        ),
        worker=controller.model_copy(
            update={"process_id": controller.process_id + 20000001}
        ),
    )
    image = ReleaseFile(
        path="gitlab.sif",
        sha256=GITLAB_IMAGE_SHA,
        size_bytes=22167199744,
        executable=False,
    )
    with prepared_case(root, node, owner_guard=native_guard, declared_image=image) as p:
        config, store = p.configuration, p.store
        b = binding(config.token.owner.job_id, real=False)
        parent = b.parent.model_copy(update={"writer": native_guard.controller})
        slurm = SiteSlurmBinding.model_validate(
            {
                **b.model_dump(),
                "parent": parent,
                "schema_version": "site-slurm-binding/1",
            }
        )
        site = SiteResourceSpec(configuration=config, slurm=slurm)
        member = parent.model_copy(
            update={
                "writer": native_guard.worker,
                "step_id": "0",
                "user_path": parent.user_path.replace("step_batch", "step_0"),
                "user_inode": parent.user_inode + 100,
                "task_inode": parent.task_inode + 100,
            }
        )
        target = SlurmStepTarget(
            execution=slurm.execution,
            step_name="synthetic-site",
            resources="cpu_only",
            launcher=native_guard.controller,
            worker=member,
        )
        proof = store.put(
            b'{"explicitly_synthetic":true}', metadata("site-step-raw/1"), guard()
        )
        ready = SiteResourceReady(
            worker=SiteWorkerReady(
                owner_guard=native_guard,
                installed_sources=sources(config.installation, guard()),
            ),
            controller=SlurmControllerStep(
                target=target,
                started_at_epoch=slurm.execution.started_at_epoch + 1,
                gpu_type=None,
                memory="1G",
            ),
            evidence=proof,
        )
        started = SiteResourceStarted(
            ready=ready,
            instance=p.native.artifacts.context.instance,
            evidence=store.put(
                b'{"explicitly_synthetic":true}',
                metadata("site-resource-fact/1"),
                guard(),
            ),
        )
        site_op = context(site.token, "site-acquire")
        journal_root = root / "original-site-journal"
        journal_root.mkdir()
        # Actual ledger transitions, with explicitly synthetic ready/started facts.
        from lab_generate_skill.adapters.clock import SystemClock
        from lab_generate_skill.runtime.lifecycle import OperationGuards
        from test_resource_journal import NoCancellation

        journal = FileResourceJournal(
            journal_root,
            site.token.owner,
            OperationGuards(SystemClock(), NoCancellation()),
            store,
        )
        registered = journal.register(site.token, context(site.token, "site-register"))
        intent = ResourceAcquisitionIntent(
            token=site.token, operation=site_op, configuration_ref=put(store, site)
        )
        acquiring = journal.begin_acquire(
            site.token, put(store, intent), registered.revision, site_op
        )
        spec_hash = hashlib.sha256(site.model_dump_json().encode()).hexdigest()
        ready_op = context(site.token, "site-ready")
        fact = dict(
            schema_version="site-resource-fact/1",
            spec_sha256=spec_hash,
            token=site.token.model_dump(mode="json"),
            state="acquired",
            operation=ready_op.model_dump(mode="json"),
            details=dict(
                ready=started.ready.model_dump(mode="json"), site_started=False
            ),
        )
        ready_ref = store.put(
            json.dumps(fact).encode(), metadata("site-resource-fact/1")
        )
        journal.advance(
            site.token, "acquired", (ready_ref,), acquiring.revision, ready_op
        )
        start_op = site_op.model_copy(
            update={
                "operation_id": "site-start",
                "parent_operation_id": site_op.operation_id,
            }
        )
        fact.update(
            operation=start_op.model_dump(mode="json"),
            details=dict(
                ready_ref=ready_ref.model_dump(mode="json"),
                started=started.instance.model_dump(mode="json"),
            ),
        )
        started = started.model_copy(
            update={
                "evidence": store.put(
                    json.dumps(fact).encode(), metadata("site-resource-fact/1")
                )
            }
        )
        qualified = qualify_existing(p, site, started)
        publication = p.records.publish(p.inputs.selection, p.inputs.request.operation)
        prepared = p.records.load(publication, p.inputs.request.operation)
        base = configuration(p.configuration.installation)
        session = BrowserSessionSpec.model_validate(
            {
                **base.spec.model_dump(),
                "scope": prepared.scope,
                "task": prepared.public_task,
            }
        )
        selected = group_browser_declaration(
            public=prepared.public_task,
            endpoint=started.instance.endpoint,
            native_account_id=1,
            prepared_ref=publication.prepared_ref,
            site_ref=put(store, started),
        )
        browser_config = BrowserWorkerConfiguration.model_validate(
            {**base.model_dump(), "spec": session, "initialization": selected}
        )
        browser_root = root / "browser"
        browser_root.mkdir()
        browser = resource_case(
            browser_root, monkeypatch, config=browser_config, store=store
        )
        browser.spec = browser.spec.model_copy(
            update={
                "slurm": browser.spec.slurm.model_copy(
                    update={
                        "execution": site.slurm.execution,
                        "parent": site.slurm.parent,
                    }
                )
            }
        )
        checks = PreparedBrowserBinding(
            publication,
            site,
            started,
            site_op,
            evidence=store,
            preparations=p.records,
            journal=journal,
            task_checks=group_prepared_browser_checks(store),
        )
        yield Case(
            p,
            browser,
            checks,
            PreparedBrowserAuthority(browser.spec, checks, browser.authority),
            qualified,
        )
