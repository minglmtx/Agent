"""Actual loop/CAS/native count/review/read ports; deliberate synthetic native tokens."""

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal
from typing import Any
from lab_generate_skill.actor.decisions import RecordedActorDecisions
from lab_generate_skill.application.actor_rejection_progress import (
    RecordedActorRejectionProgress,
)
from lab_generate_skill.actor.context_source import ADAPTIVE_ACTOR_PROTECTION_RULES
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from lab_generate_skill.adapters.models.context_tokens import ActorContextTokenCounter
from lab_generate_skill.adapters.models.context_count_review import (
    ActorContextCountReviewer,
)
from lab_generate_skill.adapters.models.local_actor import RecordedLocalActorModel
from lab_generate_skill.adapters.plans.actor_observation_sources import (
    ActorObservationSources,
)
from lab_generate_skill.application.actor_loop import RecordedActorRunner
from lab_generate_skill.application.actor_model_admission import TraceActorAuthority
from lab_generate_skill.application.actor_context_preparation import (
    ControlledActorContext,
)
from lab_generate_skill.application.actor_context_review import (
    RecordedActorContextInputs,
)
from lab_generate_skill.bootstrap.context_projection import build_actor_context
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_projection import (
    AdaptiveObservationProjection,
    ObservationTaskBinding,
)
from lab_generate_skill.domain.actor_engine import (
    LocalActorOutput,
    LocalActorParameters,
)
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.context_projection import ContextProjectionPolicy
from lab_generate_skill.domain.local_actor import LocalActorExecution
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.ports.lifecycle import OperationControl
from adaptive_observation_fixtures import ObservationSession
from actor_context_loop_fixtures import context_loop_case, ContextLoopCase
from actor_loop_fixtures import UnitAuthority
from observation_read_fixtures import policy
from retrieval_fixtures import reference
from test_run_journal import command


class AdaptiveSession(ObservationSession):
    def __init__(self, mode: str = "read") -> None:
        super().__init__()
        self.mode = mode
        self.prompts: list[ActorPrompt] = []
        self.last_prompt: ActorPrompt | None = None
        self.complete_inputs: list[str] = []

    def tokenize(
        self, request: ActorPrompt, parameters: LocalActorParameters
    ) -> tuple[int, ...]:
        self.last_prompt = request
        self.complete_inputs.append(request.prompt_version)
        full = request.prompt_version in (
            "browsergym-adaptive-full-ax-v1",
            "browsergym-adaptive-full-ax-v2",
        )
        return (1,) * (110 if full and self.mode != "small" else 30)

    def infer(
        self,
        tokens: tuple[int, ...],
        parameters: LocalActorParameters,
        control: OperationControl,
    ) -> LocalActorOutput:
        assert self.last_prompt is not None
        request = self.last_prompt
        self.prompts.append(request)
        self.calls += 1
        view = request.observation_view
        assert view is not None
        if self.mode == "duplicate":
            text = json.dumps(
                dict(
                    thought="Request the currently displayed directory.",
                    read=dict(
                        tool="list_regions",
                        snapshot_sha256=view.snapshot.observation_ref.sha256,
                        output_tokens=8,
                    ),
                )
            )
        elif self.calls == 1 and self.mode == "read":
            text = json.dumps(
                dict(
                    thought="Read the last captured row before answering.",
                    read=dict(
                        tool="read_region",
                        snapshot_sha256=view.snapshot.observation_ref.sha256,
                        output_tokens=8,
                        ranges=[
                            dict(
                                region_id="ax-line-1", unit="data_rows", start=3, end=4
                            )
                        ],
                    ),
                )
            )
        else:
            text = '{"thought":"Use the actually returned public row.","action":"send_msg_to_user(\'Done\')"}'
        return LocalActorOutput(
            text=text,
            finish_reason="stop",
            prompt_tokens=len(tokens),
            completion_tokens=2,
        )


@dataclass
class AdaptiveLoopCase:
    base: ContextLoopCase
    request: ActorRunRequest
    configuration: ActorContextConfiguration
    session: AdaptiveSession
    sources: ActorObservationSources
    runner: RecordedActorRunner
    review: ActorContextCountReviewer
    executions: list[LocalActorExecution]


def adaptive_loop_case(
    root: Path,
    *,
    mode: str = "read",
    captured_text: str | None = None,
    policy_version: Literal[
        "context-projection-policy/2", "context-projection-policy/3"
    ] = "context-projection-policy/2",
    local_supported: bool = True,
    read_policy_changes: dict[str, Any] | None = None,
) -> AdaptiveLoopCase:
    current = context_loop_case(root)
    c = current.base
    store = c.loop.store
    controls = c.loop.journal.controls
    initial = Observation.model_validate_json(
        store.read(current.request.initial_observation_ref)
    )
    text = (
        "[1] RootWebArea 'Captured public table'\n\t[2] table\n\t\t[3] row\n\t\t\t[4] columnheader Value\n"
        + "".join(
            f"\t\t[{10+i*2}] row Record-{i}\n\t\t\t[{11+i*2}] gridcell Value-{i}\n"
            for i in range(4)
        )
    )
    if captured_text is not None:
        text = captured_text
    initial = Observation.model_validate(
        {**initial.model_dump(), "text": text, "text_ref": None}
    )
    ref = reference(initial, "observation/1", "public", store)
    plan = c.loop.journal.plan.model_copy(update={"initial_observation_ref": ref})
    journal_root = root / "adaptive-journal"
    journal_root.mkdir()
    journal = FileTraceJournal(journal_root, plan, controls, store, UnitAuthority())
    journal.create(plan, command("create-adaptive-loop", attempt="attempt"))
    c.loop.journal = journal
    c.loop.browser.journal = journal
    session = AdaptiveSession(mode)
    c.loader.session = session
    read_policy = policy(
        **(
            dict(switch_tokens=80, body_target_tokens=6, body_max_tokens=8)
            | (read_policy_changes or {})
        )
    )
    binding = ObservationTaskBinding(
        site=plan.scope.task.site,
        family=plan.scope.task.family if local_supported else "unsupported_unit_family",
        contract_version=plan.scope.task.contract_version,
        split=plan.scope.task.split,
    )
    selected = ContextProjectionPolicy.model_validate(
        dict(
            schema_version=policy_version,
            role="actor",
            policy_id="unit-actual-adaptive-loop",
            implementation_sha256="a" * 64,
            software_evidence_ref=reference(
                {"synthetic_software_gate_only": True},
                "context-policy-evidence/1",
                store=store,
            ),
            protected_rules=ADAPTIVE_ACTOR_PROTECTION_RULES,
            candidate_order=("compact_full_ax", "local_ax"),
            allow_identity_fallback=True,
            forced_kind=None,
            actor_projection=AdaptiveObservationProjection(
                read_policy=read_policy, local_bindings=(binding,)
            ),
        )
    )
    profile = current.config.profiles[0]
    configuration = ActorContextConfiguration(
        policy=selected, profiles=(profile,) * plan.max_generations
    )
    request = ActorRunRequest.model_validate(
        {
            **current.request.model_dump(),
            "initial_observation_ref": ref,
            "context_configuration_ref": reference(
                configuration, "actor-context-configuration/1", store=store
            ),
        }
    )
    counter = ActorContextTokenCounter(
        c.client,
        store,
        profile,
        current.model_binding,
        current.params,
        session_id=c.client.session_id,
    )
    guard, installed = c.client.owner_guard, c.client.installed_sources
    assert guard is not None and installed is not None
    review = ActorContextCountReviewer(
        store,
        profile,
        current.model_binding,
        current.params,
        c.client.artifact,
        c.client.config,
        session_id=c.client.session_id,
        guard=guard,
        installed_sources=installed,
    )
    sources = ActorObservationSources(
        request,
        journal,
        store,
        c.loop.authority,
        controls,
        configuration,
        counter,
        review,
        rejections=RecordedActorRejectionProgress(store),
    )
    project, protection = build_actor_context(
        selected, indices=sources.index_for_public
    )
    inputs = RecordedActorContextInputs(
        store,
        c.loop.runner.deps.observations,
        project,
        protection,
        review,
        retain_inputs=True,
        request=request,
        observation_sources=sources,
    )
    context = ControlledActorContext(
        request,
        journal,
        store,
        c.loop.runner.deps.observations,
        c.loop.authority,
        controls,
        project,
        protection,
        counter,
        inputs=inputs,
        observation_sources=sources,
    )
    journal = journal.with_generation_inputs(inputs).with_reading_inputs(sources)
    c.loop.journal = journal
    c.loop.browser.journal = journal
    completed: list[LocalActorExecution] = []

    class Returns(TraceActorAuthority):
        def verify_return(
            self, execution: LocalActorExecution, control: OperationControl
        ) -> None:
            super().verify_return(execution, control)
            completed.append(execution)

    authority = Returns(
        request,
        journal,
        store,
        c.loop.runner.deps.observations,
        prepare_actor,
        c.loop.authority,
        controls,
        context=inputs,
        inputs=inputs,
    )
    model = RecordedLocalActorModel(
        c.root, c.binding, c.client, store, controls, authority, inputs=inputs
    )
    runner = RecordedActorRunner(
        replace(
            c.loop.runner.deps,
            browser=current.runner.deps.browser,
            journal=journal,
            context=context,
            model=model,
            readings=sources,
            decisions=(
                RecordedActorDecisions(store, controls, proposals=sources)
                if read_policy.schema_version == "observation-read-policy/2"
                else c.loop.runner.deps.decisions
            ),
        )
    )
    return AdaptiveLoopCase(
        current, request, configuration, session, sources, runner, review, completed
    )
