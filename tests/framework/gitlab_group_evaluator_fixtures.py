"""Complete Group/COPY evidence joins; explicit synthetic SQL/browser/model effects only."""

from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import pytest
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabGroupInitialization,
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
from lab_generate_skill.sites.gitlab.evidence_schema import (
    GroupEvidence,
    GitlabSiteCapture,
    GitlabPageCapture,
    GitlabPageHealth,
)
from lab_generate_skill.evaluators.gitlab.group import REQUIREMENTS
from gitlab_group_qualification_fixtures import QualifiedCase, qualified
from gitlab_group_preparation_fixtures import Case as PreparationCase
from gitlab_preparation_fixtures import put
from gitlab_group_fixtures import native_state
from browser_worker_fixtures import configuration
from browser_resource_fixtures import resource_case
from synthetic_browser_trace import one_return
from test_slurm_commands import guard


@dataclass
class Case:
    source: QualifiedCase
    browser: BrowserResourceSpec
    contract: EvaluationContract
    selected: GroupEvidence
    trace: InteractionTrace


@contextmanager
def evaluation_case(
    root: Path,
    node: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    saved: bool = True,
    projects_changed: bool = False,
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
                "initialization": GitlabGroupInitialization(
                    endpoint=c.started.instance.endpoint,
                    native_account_id=native_state().user.id,
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
        before = capture_pair(p, "before")
        trace = one_return(store, prepared.public_task, prepared.scope, b.op)
        (p.native.state / "group.json").write_bytes(
            native_state(inserted=saved).model_dump_json().encode()
        )
        if projects_changed:
            original_projects = (p.native.state / "projects.csv").read_bytes()
            (p.native.state / "projects.csv").write_bytes(
                original_projects.replace(b"\n", b"\r\n")
            )
        after = capture_pair(p, "after")
        contract, selected = evaluation_selection(c, b.spec, trace, before, after)
        yield Case(c, b.spec, contract, selected, trace)


def capture_pair(p: PreparationCase, label: str) -> GitlabSiteCapture:
    store = p.store
    inspection = p.native.next("inspect", "eval-capture-" + label)
    request = SiteCaptureRequest(
        inspection=inspection,
        collector_id="gitlab-group-creation",
        collector_version="1",
    )
    intent = SiteCaptureIntent(
        configuration_sha256=hashlib.sha256(
            p.configuration.model_dump_json().encode()
        ).hexdigest(),
        request=request,
    )
    result = p.native.task.capture_task(request, control=guard())
    return GitlabSiteCapture(
        intent_ref=put(store, intent), result_ref=put(store, result)
    )


def evaluation_selection(
    c: QualifiedCase,
    browser: BrowserResourceSpec,
    trace: InteractionTrace,
    before: GitlabSiteCapture,
    after: GitlabSiteCapture,
) -> tuple[EvaluationContract, GroupEvidence]:
    p, store = c.preparation, c.preparation.store
    public = browser.configuration.spec.task
    scope = browser.configuration.spec.scope
    contract = EvaluationContract(
        identity=scope.task,
        attempt_id=scope.attempt_id,
        task_contract_ref=p.inputs.request.binding_ref,
        public_task_ref=p.inputs.binding.public_task_ref,
        completion_spec_ref=p.inputs.binding.private_spec_ref,
        requirements=REQUIREMENTS,
        scope="engineering",
    )

    page_request = BrowserCaptureRequest(
        scope=scope,
        operation=trace.operation.model_copy(update={"operation_id": "eval-page"}),
        observation_sha256=trace.final_observation_ref.sha256,
        collector_id="gitlab-page-health",
        collector_version="1",
    )
    page_intent = BrowserCaptureIntent(
        configuration_sha256=hashlib.sha256(
            browser.configuration.model_dump_json().encode()
        ).hexdigest(),
        request=page_request,
    )
    page = GitlabPageHealth(
        url=public.start_url,
        title="Groups · GitLab",
        http_status=200,
        status_source="navigation_timing",
        login_page=False,
        error_page=False,
        account_id=native_state().user.id,
    )
    page_result = BrowserCaptureResult(
        request_sha256=page_request.digest,
        captured_at=datetime.now(timezone.utc),
        private_result=page.model_dump_json(),
    )
    selected = GroupEvidence(
        environment_ref=c.environment_ref,
        browser_spec_ref=put(store, browser),
        before=before,
        after=after,
        page=GitlabPageCapture(
            intent_ref=put(store, page_intent), result_ref=put(store, page_result)
        ),
        trace_ref=put(store, trace),
    )
    return contract, selected
