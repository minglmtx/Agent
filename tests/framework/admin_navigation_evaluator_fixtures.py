"""Real CAS with synthetic sealed execution/capture; no resource permissions."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import pytest
import trace_fixtures
from observation_fixtures import sample_observation
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.lifecycle import AllocationToken
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureRequest,
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.admin_navigation_browser_initialization import (
    AdminNavigationInitialization,
)
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.sites.shopping_admin.evidence_schema import (
    AdminNavigationEvidence,
    AdminNavigationPage,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_input import (
    bind_admin_navigation,
)
from lab_generate_skill.evaluators.shopping_admin.navigation import REQUIREMENTS
from evidence_control_fixtures import EvidenceFixtureStore
from browser_worker_fixtures import configuration
from browser_step_fixtures import binding
from state_contract_fixtures import scope
from test_core_contracts import reference
from test_run_journal import command
from test_slurm_commands import guard


class EvalCase:
    def __init__(
        self,
        root: Path,
        monkeypatch: pytest.MonkeyPatch,
        contracts: Any,
        final_url: str | None = None,
    ) -> None:
        self.store = EvidenceFixtureStore(root)
        native, native_ref, public = contracts[0]
        inputs = bind_admin_navigation(native, native_ref, public)
        self.public, self.spec = inputs.public_task, inputs.private_spec
        original = scope()
        bound = original.model_copy(
            update={
                "task": public.identity,
                "owner": original.owner.model_copy(update={"job_id": "4752096"}),
            }
        )
        monkeypatch.setattr(trace_fixtures, "scope", lambda: bound)
        sample = sample_observation

        def initial(task: Any, context: Any, attempt: Any) -> Any:
            value = sample(task, context, attempt)
            active = next(
                tab for tab in value.tabs if tab.tab_id == value.active_tab_id
            )
            return value.model_copy(
                update={"tabs": (active.model_copy(update={"url": public.start_url}),)}
            )

        monkeypatch.setattr(trace_fixtures, "sample_observation", initial)
        traced = trace_fixtures.fixture(self.store, outcomes=("returned",))
        url = final_url or "http://127.0.0.1:18080/admin" + self.spec.target_path
        observed = traced.observations[-1]
        active = next(
            tab for tab in observed.tabs if tab.tab_id == observed.active_tab_id
        )
        observed = observed.model_copy(
            update={"tabs": (active.model_copy(update={"url": url}),)}
        )
        final_ref = self.put(observed, "public")
        last = traced.trace.turns[-1]
        assert last.interaction is not None and last.interaction.result is not None
        raw = json.dumps(
            {
                "action_id": last.interaction.action.action_id,
                "observation_ref": final_ref.model_dump(mode="json"),
                "terminal": True,
            }
        ).encode()
        returned = self.store.put(
            raw,
            EvidenceMetadata(
                media_type="application/json",
                content_schema="browser-step-return/1",
                visibility="private",
                producer="synthetic-navigation-return",
            ),
            control=guard(),
        )
        result = last.interaction.result.model_copy(
            update={"observation_ref": final_ref, "return_ref": returned}
        )
        turn = last.model_copy(
            update={
                "interaction": last.interaction.model_copy(update={"result": result})
            }
        )
        self.trace = InteractionTrace.model_validate(
            {**traced.trace.model_dump(), "turns": (*traced.trace.turns[:-1], turn)}
        )
        self.binding = TaskBinding(
            identity=public.identity,
            registration_id="unit-navigation",
            public_task_ref=self.put(public, "public"),
            private_spec_ref=self.put(self.spec),
            baseline_ref=self.put(self.spec),
        )
        self.contract = EvaluationContract(
            identity=public.identity,
            attempt_id=bound.attempt_id,
            task_contract_ref=self.put(self.binding),
            public_task_ref=self.binding.public_task_ref,
            completion_spec_ref=self.binding.private_spec_ref,
            requirements=REQUIREMENTS,
            scope="engineering",
        )
        base = configuration()
        session = base.spec.model_copy(update={"scope": bound, "task": public})
        config = BrowserWorkerConfiguration.model_validate(
            {
                **base.model_dump(),
                "spec": session,
                "initialization": AdminNavigationInitialization(
                    endpoint="http://127.0.0.1:18080/admin",
                    prepared_ref=reference(content_schema="prepared-task/1"),
                    site_ref=reference(content_schema="site-resource-started/1"),
                    native_contract_sha256=native_ref.sha256,
                    start_path=self.spec.start_path,
                ),
            }
        )
        token = AllocationToken(
            allocation_id="browser",
            owner=bound.owner,
            scope="attempt",
            attempt_id=bound.attempt_id,
            resource_kind="browser",
            expected_resource_id="unit-browser",
            provider_id="fixed-browser-worker",
            provider_version="3",
            recovery_ref=reference(content_schema="recovery-plan/1"),
        )
        self.browser = BrowserResourceSpec(
            token=token, configuration=config, slurm=binding("4752096", real=False)
        )
        self.page = AdminNavigationPage(
            url=url, heading=self.spec.heading, login=False, page_error=False
        )
        intent_ref, result_ref = self.page_pair()
        self.selected = AdminNavigationEvidence(
            scope=bound,
            browser_spec_ref=self.put(self.browser),
            trace_ref=self.put(self.trace),
            page_intent_ref=intent_ref,
            page_result_ref=result_ref,
        )

    def put(self, value: Contract, visibility: Any = "private") -> EvidenceRef:
        return self.store.put(
            value.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema=str(value.model_dump()["schema_version"]),
                visibility=visibility,
                producer="synthetic-navigation-evaluation",
            ),
            control=guard(),
        )

    def page_pair(self, **updates: Any) -> tuple[EvidenceRef, EvidenceRef]:
        request = BrowserCaptureRequest(
            scope=self.trace.scope,
            operation=command("navigation-page", attempt=self.trace.scope.attempt_id),
            observation_sha256=self.trace.final_observation_ref.sha256,
            collector_id="admin-navigation-page",
            collector_version="1",
        )
        request = request.model_copy(update=updates)
        intent = BrowserCaptureIntent(
            configuration_sha256=hashlib.sha256(
                self.browser.configuration.model_dump_json().encode()
            ).hexdigest(),
            request=request,
        )
        result = BrowserCaptureResult(
            request_sha256=request.digest,
            captured_at=datetime.now(timezone.utc),
            private_result=self.page.model_dump_json(),
        )
        return self.put(intent), self.put(result)
