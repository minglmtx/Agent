"""Real complete evidence joins with synthetic native/browser/model effects only."""

from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import pytest
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.reddit_browser_initialization import (
    RedditNativeImageInitialization,
)
from lab_generate_skill.domain.site_capture import SiteCaptureIntent, SiteCaptureRequest
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureRequest,
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.sites.reddit.evidence_schema import (
    ImageEvidence,
    ImageSiteCapture,
    ImagePageCapture,
    RedditPageHealth,
)
from lab_generate_skill.evaluators.reddit.native_image import REQUIREMENTS
from reddit_qualification_fixtures import QualifiedCase, qualified
from reddit_preparation_fixtures import put
from reddit_image_state_fixtures import posted_data
from lab_generate_skill.sites.reddit.native_schema import NativeCapture
from lab_generate_skill.bootstrap.reddit_browser_files import reddit_photo_plan
import json
from browser_worker_fixtures import configuration
from browser_resource_fixtures import resource_case
from reddit_evaluator_actor_fixture import recorded_trace
from test_slurm_commands import guard


@dataclass
class Case:
    source: QualifiedCase
    browser: BrowserResourceSpec
    contract: EvaluationContract
    selected: ImageEvidence
    trace: InteractionTrace


@contextmanager
def evaluation_case(
    root: Path,
    node: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    saved: bool = True,
    issued_title: bool = True,
) -> Iterator[Case]:
    with qualified(root, node) as c:
        p, store = c.preparation, c.preparation.store
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
        config = BrowserWorkerConfiguration.model_validate(
            {
                **base.model_dump(),
                "spec": session,
                "initialization": RedditNativeImageInitialization(
                    endpoint=c.started.instance.endpoint,
                    native_account_id=p.native.reader.initial.account.id,
                    native_account_username=p.native.reader.initial.account.username,
                    task_files=reddit_photo_plan(
                        prepared.scope,
                        p.configuration.files.node_root + "/browser-uploads",
                    ),
                    prepared_ref=publication.prepared_ref,
                    site_ref=c.environment.site_started_ref,
                ),
            }
        )
        path = root / "browser"
        path.mkdir()
        b = resource_case(path, monkeypatch, config=config, store=store)
        # Same explicitly synthetic original controller declaration as the
        # native qualifier; no live worker or cgroup is claimed by this fixture.
        b.spec = b.spec.model_copy(
            update={
                "slurm": b.spec.slurm.model_copy(
                    update={
                        "execution": c.site.slurm.execution,
                        "parent": c.site.slurm.parent,
                    }
                )
            }
        )
        contract = EvaluationContract(
            identity=prepared.scope.task,
            attempt_id=prepared.scope.attempt_id,
            task_contract_ref=p.inputs.request.binding_ref,
            public_task_ref=p.inputs.binding.public_task_ref,
            completion_spec_ref=p.inputs.binding.private_spec_ref,
            requirements=REQUIREMENTS,
            scope="engineering",
        )

        def capture(label: str) -> ImageSiteCapture:
            inspection = p.native.next("inspect", "eval-capture-" + label)
            request = SiteCaptureRequest(
                inspection=inspection,
                collector_id="reddit-native-image",
                collector_version="1",
            )
            intent = SiteCaptureIntent(
                configuration_sha256=hashlib.sha256(
                    p.configuration.model_dump_json().encode()
                ).hexdigest(),
                request=request,
            )
            result = p.native.task.capture_task(request, control=guard())
            return ImageSiteCapture(
                intent_ref=put(store, intent), result_ref=put(store, result)
            )

        before = capture("before")
        journal = recorded_trace(
            root / "actor-trace", store, b.spec, b.op, issued_title=issued_title
        )
        trace = journal.project().sealed
        assert trace is not None
        p.native.reader.value = NativeCapture.model_validate_json(
            json.dumps(posted_data())
            if saved
            else p.native.reader.initial.capture.model_dump_json()
        )
        after = capture("after")
        page_request = BrowserCaptureRequest(
            scope=prepared.scope,
            operation=b.op.model_copy(update={"operation_id": "eval-page"}),
            observation_sha256=trace.final_observation_ref.sha256,
            collector_id="reddit-page-health",
            collector_version="1",
        )
        page_intent = BrowserCaptureIntent(
            configuration_sha256=hashlib.sha256(
                config.model_dump_json().encode()
            ).hexdigest(),
            request=page_request,
        )
        page = RedditPageHealth(
            url=prepared.public_task.start_url,
            title="Submit · Reddit",
            http_status=200,
            status_source="navigation_timing",
            login_page=False,
            error_page=False,
        )
        page_result = BrowserCaptureResult(
            request_sha256=page_request.digest,
            captured_at=datetime.now(timezone.utc),
            private_result=page.model_dump_json(),
        )
        selected = ImageEvidence(
            environment_ref=c.environment_ref,
            browser_spec_ref=put(store, b.spec),
            before=before,
            after=after,
            page=ImagePageCapture(
                intent_ref=put(store, page_intent), result_ref=put(store, page_result)
            ),
            trace_ref=put(store, trace),
            trace_snapshot_ref=put(store, journal),
        )
        yield Case(c, b.spec, contract, selected, trace)
