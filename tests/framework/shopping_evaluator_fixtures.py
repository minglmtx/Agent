"""Real CAS and complete typed fake native/page/model/browser records; no rights."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.site_capture import SiteCaptureIntent, SiteCaptureRequest
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureRequest,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.browser import BrowserAction, StepResult
from lab_generate_skill.domain.browser_action_protocol import PROTOCOL
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.actor_generation import ActorGeneration, ActorDecision
from lab_generate_skill.domain.interaction import InteractionEvent
from lab_generate_skill.domain.trace import InteractionTrace, TraceTurn
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.sites.shopping.evidence_schema import (
    OrderEtaEvidence,
    SiteCaptureEvidence,
    PageCaptureEvidence,
    ShoppingPageHealth,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_state import (
    OrderEtaState,
    NativeEtaFixture,
    OrderEtaExecutionInput,
)
from lab_generate_skill.sites.shopping.query_state import (
    QueryProtectedState,
    QueryProtection,
    LocalMail,
)
from lab_generate_skill.sites.shopping.native_static import NativeStaticPublication
from lab_generate_skill.sites.shopping.static_program import NATIVE_STATIC
from lab_generate_skill.sites.shopping.tasks.order_eta_policy import (
    order_eta_initial_spec,
)
from lab_generate_skill.evaluators.shopping.order_eta import REQUIREMENTS
from lab_generate_skill.bootstrap.shopping_order_eta import load_order_eta_inputs
from evidence_control_fixtures import EvidenceFixtureStore
from test_shopping_order_eta_inputs import FIXTURE, public_task
from shopping_task_fixtures import protection, native_fixture, request
from shopping_services_fixtures import Commands
from observation_fixtures import sample_observation
from state_contract_fixtures import scope
from test_run_journal import command
from test_slurm_commands import guard


class EtaEvalCase:
    def __init__(self, root: Path) -> None:
        self.store = EvidenceFixtureStore(root)
        raw = FIXTURE.read_bytes()
        native = self.raw(raw, "shopping-native-contract/1")
        inputs = load_order_eta_inputs(raw, native, public_task())
        self.public, self.spec = inputs.public_task, inputs.private_spec
        self.scope: StateScope = scope().model_copy(
            update={"task": self.public.identity}
        )
        self.binding = TaskBinding(
            identity=self.public.identity,
            registration_id="synthetic-eta",
            public_task_ref=self.put(self.public, "public"),
            private_spec_ref=self.put(self.spec),
            baseline_ref=self.put(order_eta_initial_spec(self.public.identity)),
        )
        self.contract = EvaluationContract(
            identity=self.public.identity,
            attempt_id=self.scope.attempt_id,
            task_contract_ref=self.put(self.binding),
            public_task_ref=self.binding.public_task_ref,
            completion_spec_ref=self.binding.private_spec_ref,
            requirements=REQUIREMENTS,
            scope="engineering",
        )
        self.before = OrderEtaState(
            task=self.public.identity,
            fixture=NativeEtaFixture.model_validate_json(json.dumps(native_fixture())),
            protected=QueryProtectedState(
                protection=QueryProtection.model_validate_json(
                    json.dumps(protection(True))
                ),
                core_fingerprint="c" * 64,
                native_static_assets=NativeStaticPublication.model_validate_json(
                    Commands(root).run((NATIVE_STATIC,), guard())
                ),
                local_mail=LocalMail(
                    backend="local_sendmail_capture_v1",
                    messages=(),
                    external_delivery=False,
                ),
            ),
        )
        self.after = self.before
        self.trace = self.trace_with_answer()
        self.health = ShoppingPageHealth(
            url=self.public.start_url,
            http_status=200,
            status_source="navigation_timing",
            title="Account Dashboard",
            login_page=False,
            error_page=False,
        )
        self.selection = OrderEtaEvidence(
            before=self.site_pair(self.before, "before"),
            after=self.site_pair(self.after, "after"),
            page=self.page_pair(),
            trace_ref=self.put(self.trace),
        )

    def raw(self, data: bytes, schema: str, visibility: Any = "private") -> EvidenceRef:
        return self.store.put(
            data,
            EvidenceMetadata(
                media_type="application/json",
                content_schema=schema,
                visibility=visibility,
                producer="synthetic-shopping-evaluation",
            ),
            control=guard(),
        )

    def put(self, value: Contract, visibility: Any = "private") -> EvidenceRef:
        return self.raw(
            value.model_dump_json().encode(),
            str(value.model_dump()["schema_version"]),
            visibility,
        )

    def trace_with_answer(
        self,
        answer: str | None = '{"estimated_delivery_date":"2023-02-03"}',
        error: str = "",
    ) -> InteractionTrace:
        initial = sample_observation(
            self.public.identity, self.scope.context_id, self.scope.attempt_id
        )
        initial = initial.model_copy(
            update={
                "tabs": tuple(
                    t.model_copy(update={"url": self.public.start_url})
                    for t in initial.tabs
                )
            }
        )
        initial_ref = self.put(initial, "public")
        action = BrowserAction(
            action_id="answer",
            protocol_id=PROTOCOL,
            name="send_msg_to_user" if answer is not None else "click",
            payload=(
                "send_msg_to_user(" + repr(answer) + ")"
                if answer is not None
                else "click('2')"
            ),
        )
        op = command("browser-answer", attempt=self.scope.attempt_id)
        observed = initial.model_copy(
            update={
                "observation_id": "after-answer",
                "sequence": 1,
                "last_action_error": error,
            }
        )
        observed_ref = self.put(observed, "public")
        returned = BrowserReadout(
            schema_version="browser-step-return/1",
            scope=self.scope,
            operation=op,
            action=action,
            observation=observed,
            events=(),
            environment_reward=0.0,
            terminated=False,
            truncated=False,
            protocol_terminal=answer is not None,
        )
        result = StepResult(
            scope=self.scope,
            operation=op,
            action_id=action.action_id,
            before_observation_ref=initial_ref,
            observation_ref=observed_ref,
            return_ref=self.put(returned),
            terminal=returned.protocol_terminal,
        )
        generation = ActorGeneration(
            scope=self.scope,
            operation=command("generation", attempt=self.scope.attempt_id),
            generation_id="generation",
            request_id="request",
            before_observation_ref=initial_ref,
            input_ref=self.raw(b"{}", "actor-model-input/1"),
            parameters_ref=self.raw(b"{}", "model-parameters/1"),
            status="completed",
            response_ref=self.raw(b"{}", "actor-model-response/1"),
            failure_ref=None,
        )
        event = InteractionEvent(
            scope=self.scope,
            operation=op,
            generation_id=generation.generation_id,
            action=action,
            before_observation_ref=initial_ref,
            outcome="returned",
            result=result,
        )
        turn = TraceTurn(
            generation=generation,
            decision=ActorDecision(
                generation_id=generation.generation_id, outcome="action", action=action
            ),
            interaction=event,
        )
        return InteractionTrace(
            scope=self.scope,
            operation=command("seal", attempt=self.scope.attempt_id),
            initial_observation_ref=initial_ref,
            max_generations=1,
            max_interactions=1,
            turns=(turn,),
            stop_reason="finished" if result.terminal else "interaction_limit",
            stop_evidence_ref=self.raw(b"{}", "trace-stop/1"),
        )

    def site_pair(
        self, state: OrderEtaState, label: str, **updates: Any
    ) -> SiteCaptureEvidence:
        inspection = request(
            "inspect", "capture-" + label, self.raw(b"{}", "shopping-eta-recovery/1")
        ).model_copy(
            update={
                "task": self.public.identity,
                "binding_ref": self.contract.task_contract_ref,
                "private_input": OrderEtaExecutionInput(
                    spec=self.spec
                ).model_dump_json(),
            }
        )
        inspection = inspection.model_copy(
            update={
                "operation": inspection.operation.model_copy(
                    update={
                        "run_id": self.scope.owner.run_id,
                        "owner_id": self.scope.owner.owner_id,
                        "attempt_id": self.scope.attempt_id,
                    }
                )
            }
        )
        inspection = inspection.model_copy(update=updates)
        req = SiteCaptureRequest(
            inspection=inspection,
            collector_id="shopping-order-eta",
            collector_version="1",
        )
        return SiteCaptureEvidence(
            intent_ref=self.put(
                SiteCaptureIntent(configuration_sha256="a" * 64, request=req)
            ),
            result_ref=self.put(
                SiteTaskResult(
                    request_sha256=req.digest, private_result=state.model_dump_json()
                )
            ),
        )

    def page_pair(self, **updates: Any) -> PageCaptureEvidence:
        req = BrowserCaptureRequest(
            scope=self.trace.scope,
            operation=command("page", attempt=self.scope.attempt_id),
            observation_sha256=self.trace.final_observation_ref.sha256,
            collector_id="shopping-page-health",
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
