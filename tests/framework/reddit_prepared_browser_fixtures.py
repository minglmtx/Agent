"""Original CAS/preparation/resource journal joins with explicit synthetic services."""

from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import pytest
from lab_generate_skill.adapters.ledger.resource_journal import FileResourceJournal
from lab_generate_skill.adapters.plans.prepared_browser import PreparedBrowserBinding
from lab_generate_skill.adapters.browsergym.prepared_authority import (
    PreparedBrowserAuthority,
)
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.reddit_browser_initialization import (
    RedditNativeImageInitialization,
)
from lab_generate_skill.bootstrap.reddit_browser_files import reddit_photo_plan
from lab_generate_skill.bootstrap.reddit_image_records import (
    reddit_prepared_browser_checks,
)
from reddit_qualification_fixtures import qualified, QualifiedCase
from reddit_preparation_fixtures import put, metadata
from browser_resource_fixtures import ResourceCase, resource_case
from browser_worker_fixtures import configuration
from test_resource_journal import context


@dataclass
class Case:
    qualified: QualifiedCase
    browser: ResourceCase
    binding: PreparedBrowserBinding
    authority: PreparedBrowserAuthority


@contextmanager
def bound(root: Path, node: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Case]:
    with qualified(root, node) as q:
        p, store = q.preparation, q.preparation.store
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
        site_op = context(q.site.token, "site-acquire")
        journal_root = root / "original-site-journal"
        journal_root.mkdir()
        # Actual ledger transitions, with explicitly synthetic ready/started facts.
        from lab_generate_skill.adapters.clock import SystemClock
        from lab_generate_skill.runtime.lifecycle import OperationGuards
        from test_resource_journal import NoCancellation

        journal = FileResourceJournal(
            journal_root,
            q.site.token.owner,
            OperationGuards(SystemClock(), NoCancellation()),
            store,
        )
        registered = journal.register(
            q.site.token, context(q.site.token, "site-register")
        )
        intent = ResourceAcquisitionIntent(
            token=q.site.token, operation=site_op, configuration_ref=put(store, q.site)
        )
        acquiring = journal.begin_acquire(
            q.site.token, put(store, intent), registered.revision, site_op
        )
        spec_hash = hashlib.sha256(q.site.model_dump_json().encode()).hexdigest()
        ready_op = context(q.site.token, "site-ready")
        fact = dict(
            schema_version="site-resource-fact/1",
            spec_sha256=spec_hash,
            token=q.site.token.model_dump(mode="json"),
            state="acquired",
            operation=ready_op.model_dump(mode="json"),
            details=dict(
                ready=q.started.ready.model_dump(mode="json"), site_started=False
            ),
        )
        ready_ref = store.put(
            json.dumps(fact).encode(), metadata("site-resource-fact/1")
        )
        journal.advance(
            q.site.token, "acquired", (ready_ref,), acquiring.revision, ready_op
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
                started=q.started.instance.model_dump(mode="json"),
            ),
        )
        started = q.started.model_copy(
            update={
                "evidence": store.put(
                    json.dumps(fact).encode(), metadata("site-resource-fact/1")
                )
            }
        )
        selected = RedditNativeImageInitialization(
            endpoint=started.instance.endpoint,
            native_account_id=p.native.reader.initial.account.id,
            native_account_username=p.native.reader.initial.account.username,
            prepared_ref=publication.prepared_ref,
            site_ref=put(store, started),
            task_files=reddit_photo_plan(
                prepared.scope, p.configuration.files.node_root + "/browser-uploads"
            ),
        )
        config = BrowserWorkerConfiguration.model_validate(
            {**base.model_dump(), "spec": session, "initialization": selected}
        )
        browser_root = root / "browser"
        browser_root.mkdir()
        b = resource_case(browser_root, monkeypatch, config=config, store=store)
        b.spec = b.spec.model_copy(
            update={
                "slurm": b.spec.slurm.model_copy(
                    update={
                        "execution": q.site.slurm.execution,
                        "parent": q.site.slurm.parent,
                    }
                )
            }
        )
        binding = PreparedBrowserBinding(
            publication,
            q.site,
            started,
            site_op,
            evidence=store,
            preparations=p.records,
            journal=journal,
            task_checks=reddit_prepared_browser_checks(store),
        )
        authority = PreparedBrowserAuthority(b.spec, binding, b.authority)
        yield Case(q, b, binding, authority)
