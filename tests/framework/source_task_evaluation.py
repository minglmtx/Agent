"""Final page capture and pure task judgment, before restoring the original site."""

from datetime import datetime, timezone, timedelta
import hashlib
from typing import Any
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from lab_generate_skill.adapters.browsergym.worker_client import (
    SupervisedBrowserSession,
)
from lab_generate_skill.adapters.browsergym.recorded_capture import (
    RecordedBrowserCapture,
)
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureRequest,
    BrowserCaptureIntent,
)
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping_admin.evidence_schema import (
    ProductDescriptionEvidence,
    SiteCaptureEvidence,
    PageCaptureEvidence,
)
from lab_generate_skill.evaluators.shopping_admin.product_description import (
    ProductDescriptionEvaluator,
    REQUIREMENTS,
)
from lab_generate_skill.sites.shopping.evidence_schema import OrderEtaEvidence
from lab_generate_skill.evaluators.shopping.order_eta import (
    OrderEtaEvaluator,
    REQUIREMENTS as ETA_REQUIREMENTS,
)
from browser_resource_fixtures import ResourceCase
from qualified_source_native import QualifiedSource
from test_slurm_commands import guard


def final_page(
    source: QualifiedSource, browser: ResourceCase, session: EvidenceBrowserSession
) -> PageCaptureEvidence:
    assert session.observation_ref is not None and isinstance(
        session.engine, SupervisedBrowserSession
    )
    request = BrowserCaptureRequest(
        scope=browser.spec.configuration.spec.scope,
        operation=browser.op.model_copy(
            update={
                "operation_id": "source-final-page",
                "deadline": datetime.now(timezone.utc) + timedelta(seconds=20),
            }
        ),
        observation_sha256=session.observation_ref.sha256,
        collector_id=(
            "reddit-page-health"
            if source.c.spec.configuration.site_id == "reddit"
            else (
                "gitlab-page-health"
                if source.c.spec.configuration.site_id == "gitlab"
                else (
                    "shopping-page-health"
                    if source.c.spec.configuration.site_id == "shopping"
                    else "admin-page-health"
                )
            )
        ),
        collector_version="1",
    )

    class Authority:
        def verify_capture(
            self,
            configuration: BrowserWorkerConfiguration,
            req: BrowserCaptureRequest,
            intent_ref: EvidenceRef,
            control: OperationControl,
        ) -> None:
            assert configuration == browser.spec.configuration and req == request
            assert (
                session.observation_ref is not None
                and req.observation_sha256 == session.observation_ref.sha256
            )
            intent = BrowserCaptureIntent.model_validate_json(
                source.c.evidence.read(intent_ref, control)
            )
            assert (
                intent.request == req
                and intent.configuration_sha256
                == hashlib.sha256(configuration.model_dump_json().encode()).hexdigest()
            )
            assert (
                browser.journal.read(
                    browser.spec.token,
                    req.operation.model_copy(
                        update={"operation_id": "final-page-resource-read"}
                    ),
                ).state
                == "acquired"
            )
            control.checkpoint()

    recorder = RecordedBrowserCapture(session.engine, source.c.evidence, Authority())
    ref = recorder.capture(request, control=guard(20))
    assert recorder.intent_ref is not None
    return PageCaptureEvidence(intent_ref=recorder.intent_ref, result_ref=ref)


def judge_source_task(
    source: QualifiedSource, facts: dict[str, Any], actor: dict[str, Any]
) -> dict[str, Any]:
    if source.c.spec.configuration.site_id == "reddit":
        from reddit_task_evaluation import judge_source_task as reddit_judgment

        return reddit_judgment(source, facts, actor)
    if source.c.spec.configuration.site_id == "gitlab":
        from gitlab_task_evaluation import judge_source_task as gitlab_judgment

        return gitlab_judgment(source, facts, actor)
    n = source.native

    def site_pair(label: str) -> SiteCaptureEvidence:
        value = facts["catalog_" + label]
        return SiteCaptureEvidence(
            intent_ref=EvidenceRef.model_validate(value["intent_ref"]),
            result_ref=EvidenceRef.model_validate(value["result_ref"]),
        )

    # Both site evidence contracts share the same original capture-pair shapes.
    selection_type = (
        OrderEtaEvidence
        if source.c.spec.configuration.site_id == "shopping"
        else ProductDescriptionEvidence
    )
    selected = selection_type.model_validate(
        dict(
            before=site_pair("before").model_dump(),
            after=site_pair("after").model_dump(),
            page=(
                None
                if actor.get("page_capture") is None
                else PageCaptureEvidence.model_validate(
                    actor["page_capture"]
                ).model_dump()
            ),
            trace_ref=(
                None
                if actor.get("trace_ref") is None
                else EvidenceRef.model_validate(actor["trace_ref"])
            ),
        )
    )
    contract = EvaluationContract(
        identity=n.public.identity,
        attempt_id=source.saved["baseline_inputs"].prepared.scope.attempt_id,
        task_contract_ref=n.binding_ref,
        public_task_ref=n.binding.public_task_ref,
        completion_spec_ref=n.binding.private_spec_ref,
        requirements=(
            ETA_REQUIREMENTS if isinstance(selected, OrderEtaEvidence) else REQUIREMENTS
        ),
        scope="engineering",
    )
    evaluator = (
        OrderEtaEvaluator(selected)
        if isinstance(selected, OrderEtaEvidence)
        else ProductDescriptionEvaluator(selected)
    )
    result = evaluator.evaluate(contract, source.c.evidence, guard(30))
    return dict(
        selection_ref=n.put(selected).model_dump(mode="json"),
        contract_ref=n.put(contract).model_dump(mode="json"),
        evaluation_ref=n.put(result).model_dump(mode="json"),
        evaluation=result.model_dump(mode="json"),
    )
