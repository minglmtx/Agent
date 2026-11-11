"""Real CAS/trace/once marker with explicit synthetic worker and authority."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from lab_generate_skill.adapters.models.local_actor import RecordedLocalActorModel
from lab_generate_skill.adapters.models.actor_worker_client import SupervisedActorEngine
from lab_generate_skill.adapters.models.actor_worker_protocol import decode_command
from lab_generate_skill.domain.local_actor import (
    LocalActorBinding,
    LocalActorCall,
    LocalActorExecution,
)
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.trace_events import GenerationIntent
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.actor.prompting import prepare_actor
from actor_loop_fixtures import case as loop_case, LoopCase
from actor_worker_fixtures import worker_case, UnitChannel
from actor_engine_fixtures import Loader
from retrieval_fixtures import reference
from test_actor_protocol import turn
from test_run_journal import command


class Authority:
    def __init__(
        self, loop: LoopCase, client: SupervisedActorEngine, binding: LocalActorBinding
    ) -> None:
        self.loop, self.client, self.binding = loop, client, binding
        self.denied = False
        self.completed: list[LocalActorExecution] = []
        self.read_op = command("local-authority-read", attempt="attempt")

    def verify(
        self,
        call: LocalActorCall,
        prompt: ActorPrompt,
        parameters: LocalActorParameters,
        guard: ProcessOwnerGuard,
        phase: Literal["preflight", "dispatch"],
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if self.denied:
            raise PermissionError("Synthetic authority denied")
        assert call.binding == self.binding and guard == self.client.owner_guard
        pending = self.loop.journal.read(self.read_op).project().intent
        if (phase == "dispatch" and pending != call.intent) or (
            phase == "preflight" and pending is not None
        ):
            raise OwnershipConflict("Unit authority needs original trace phase")
        assert (
            self.loop.store.read(call.intent.input_ref)
            == prompt.model_dump_json().encode()
        )
        assert (
            self.loop.store.read(call.intent.parameters_ref)
            == parameters.model_dump_json().encode()
        )

    def verify_return(
        self, execution: LocalActorExecution, control: OperationControl
    ) -> None:
        control.checkpoint()
        assert execution.call.binding == self.binding
        actual = decode_command(self.loop.store.read(execution.command_ref))
        assert actual.session_id == self.binding.resource.expected_resource_id
        self.completed.append(execution)


@dataclass
class Case:
    root: Path
    loop: LoopCase
    loader: Loader
    client: SupervisedActorEngine
    channel: UnitChannel
    binding: LocalActorBinding
    authority: Authority
    model: RecordedLocalActorModel
    intent: GenerationIntent
    event_op: OperationContext

    def new_model(self) -> RecordedLocalActorModel:
        return RecordedLocalActorModel(
            self.root,
            self.binding,
            self.client,
            self.loop.store,
            self.loop.journal.controls,
            self.authority,
        )


def case(root: Path) -> Case:
    loop = loop_case(root)
    worker_root = root / "worker"
    worker_root.mkdir()
    _, loader, _, params, control, _, channel, client = worker_case(worker_root)
    client.configure(control)
    token = loop.request.model_allocation.model_copy(
        update={"provider_id": "fixed-actor-worker", "expected_resource_id": "session"}
    )
    binding = LocalActorBinding(
        resource=token,
        release_ref=reference({}, "release-manifest/1", store=loop.store),
        model_binding_ref=reference({}, "model-binding/1", store=loop.store),
        spec_ref=reference({}, "actor-resource-spec/1", store=loop.store),
        acquired_ref=reference({}, "actor-resource-fact/1", store=loop.store),
        cleanup_seconds=15,
    )
    authority = Authority(loop, client, binding)
    calls = root / "calls"
    calls.mkdir()
    model = RecordedLocalActorModel(
        calls, binding, client, loop.store, loop.journal.controls, authority
    )
    op = command("local-model-call", attempt="attempt").model_copy(
        update={
            "allocation_id": token.allocation_id,
            "recovery_ref": token.recovery_ref,
        }
    )
    intent = GenerationIntent(
        scope=loop.request.scope,
        operation=op,
        generation_id="generation",
        request_id="request",
        before_observation_ref=loop.request.initial_observation_ref,
        input_ref=reference(
            prepare_actor(turn()), "actor-model-input/1", store=loop.store
        ),
        parameters_ref=reference(params, "model-parameters/1", store=loop.store),
    )
    return Case(
        calls,
        loop,
        loader,
        client,
        channel,
        binding,
        authority,
        model,
        intent,
        command("local-plan-call", attempt="attempt"),
    )
