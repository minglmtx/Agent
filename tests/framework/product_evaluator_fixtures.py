"""Real CAS with explicitly synthetic captured product/page/trace facts."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import pytest
import trace_fixtures
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.site_capture import SiteCaptureRequest, SiteCaptureIntent
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureRequest,
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.sites.shopping_admin.evidence_schema import (
    SiteCaptureEvidence,
    PageCaptureEvidence,
    ProductDescriptionEvidence,
    AdminPageHealth,
    ProductCatalogState,
)
from lab_generate_skill.evaluators.shopping_admin.product_description import (
    REQUIREMENTS,
)
from evidence_control_fixtures import EvidenceFixtureStore
from test_admin_description_inputs import load, FIXTURE
from test_site_task_execution import request
from test_admin_product_catalog import state
from state_contract_fixtures import scope
from test_run_journal import command
from test_slurm_commands import guard


class EvalCase:
    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.store = EvidenceFixtureStore(root)
        inputs = load(FIXTURE.read_bytes())
        self.public, self.spec = inputs.public_task, inputs.private_spec
        bound = scope().model_copy(update={"task": self.public.identity})
        monkeypatch.setattr(trace_fixtures, "scope", lambda: bound)
        self.trace = trace_fixtures.fixture(self.store, outcomes=("returned",)).trace
        self.binding = TaskBinding(
            identity=self.public.identity,
            registration_id="engineering-description",
            public_task_ref=self.put(self.public, "public"),
            private_spec_ref=self.put(self.spec),
            baseline_ref=self.put(self.spec),
        )
        self.contract = EvaluationContract(
            identity=self.public.identity,
            attempt_id=bound.attempt_id,
            task_contract_ref=self.put(self.binding),
            public_task_ref=self.binding.public_task_ref,
            completion_spec_ref=self.binding.private_spec_ref,
            requirements=REQUIREMENTS,
            scope="engineering",
        )
        self.before = state()
        row = json.loads(self.before.target_record_json or "{}")
        row["description"] = "<p>" + self.spec.description + "</p>"
        self.after = state(target_record_json=json.dumps(row))
        self.health = AdminPageHealth(
            url=self.public.start_url, login=False, page_error=False
        )
        self.selection = ProductDescriptionEvidence(
            before=self.site_pair(self.before, "before"),
            after=self.site_pair(self.after, "after"),
            page=self.page_pair(),
            trace_ref=self.put(self.trace),
        )

    def put(self, value: Contract, visibility: Any = "private") -> EvidenceRef:
        return self.store.put(
            value.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema=value.model_dump()["schema_version"],
                visibility=visibility,
                producer="synthetic-evaluation-fixture",
            ),
            control=guard(),
        )

    def site_pair(
        self, catalog: ProductCatalogState, label: str, **updates: Any
    ) -> SiteCaptureEvidence:
        inspection = request("inspect", "capture-" + label).model_copy(
            update={"binding_ref": self.contract.task_contract_ref}
        )
        inspection = inspection.model_copy(update=updates)
        req = SiteCaptureRequest(
            inspection=inspection,
            collector_id="admin-product-catalog",
            collector_version="1",
        )
        return SiteCaptureEvidence(
            intent_ref=self.put(
                SiteCaptureIntent(configuration_sha256="a" * 64, request=req)
            ),
            result_ref=self.put(
                SiteTaskResult(
                    request_sha256=req.digest, private_result=catalog.model_dump_json()
                )
            ),
        )

    def page_pair(self, **updates: Any) -> PageCaptureEvidence:
        req = BrowserCaptureRequest(
            scope=self.trace.scope,
            operation=command("capture-page", attempt="attempt"),
            observation_sha256=self.trace.final_observation_ref.sha256,
            collector_id="admin-page-health",
            collector_version="1",
        )
        req = req.model_copy(update=updates)
        return PageCaptureEvidence(
            intent_ref=self.put(
                BrowserCaptureIntent(configuration_sha256="b" * 64, request=req)
            ),
            result_ref=self.put(
                BrowserCaptureResult(
                    request_sha256=req.digest,
                    captured_at=datetime.now(timezone.utc),
                    private_result=self.health.model_dump_json(),
                )
            ),
        )
