"""Real trace/CAS and once-only model, explicit synthetic source/browser rights."""

from dataclasses import replace
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.application.actor_model_admission import TraceActorAuthority
from lab_generate_skill.application.actor_loop_inputs import prepare_turn
from lab_generate_skill.application.actor_generation import (
    execute_actor_generation,
    ActorDispatchFailure,
)
from lab_generate_skill.application.actor_loop import RecordedActorRunner
from lab_generate_skill.adapters.models.local_actor import RecordedLocalActorModel
from lab_generate_skill.domain.local_actor import LocalActorCall, LocalActorExecution
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_engine import LocalActorOutput
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.trace_events import GenerationPlanned
from lab_generate_skill.ports.lifecycle import OperationControl
from local_actor_fixtures import case, Case
from test_local_actor import dispatch
from retrieval_fixtures import reference


def bound(
    c: Case,
) -> tuple[ActorRunRequest, TraceActorAuthority, RecordedLocalActorModel]:
    d = c.loop.runner.deps
    request = c.loop.request.model_copy(
        update={
            "model_allocation": c.binding.resource,
            "parameters_refs": (c.intent.parameters_ref,)
            * len(c.loop.request.parameters_refs),
            "operation": c.loop.request.operation.model_copy(
                update={"deadline": c.intent.operation.deadline}
            ),
        }
    )
    authority = TraceActorAuthority(
        request,
        c.loop.journal,
        c.loop.store,
        d.observations,
        d.project,
        c.loop.authority,
        c.loop.journal.controls,
    )
    snapshot = c.loop.journal.read(c.authority.read_op)
    prompt = prepare_turn(
        request,
        snapshot,
        c.intent.operation,
        c.loop.journal.controls.bind(c.intent.operation),
        c.loop.store,
        d.observations,
        d.project,
    )
    c.intent = c.intent.model_copy(
        update={
            "input_ref": reference(prompt, "actor-model-input/1", store=c.loop.store)
        }
    )
    model = RecordedLocalActorModel(
        c.root, c.binding, c.client, c.loop.store, c.loop.journal.controls, authority
    )
    return request, authority, model


def test_original_trace_input_to_one_actual_recorded_exchange(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = case(tmp_path)
    _, authority, model = bound(c)
    completed: list[LocalActorExecution] = []
    verify = authority.verify_return

    def observed(execution: LocalActorExecution, control: OperationControl) -> None:
        verify(execution, control)
        completed.append(execution)

    monkeypatch.setattr(authority, "verify_return", observed)
    result = execute_actor_generation(
        dispatch(c), c.loop.journal, model, c.loop.journal.controls
    )
    assert result.project().generation is not None and c.loader.session.calls == 1
    assert c.loop.authority.calls >= 2 and len(completed) == 1
    verify(completed[0], c.loop.journal.controls.bind(c.intent.operation))
    with pytest.raises(ActorDispatchFailure):
        execute_actor_generation(
            dispatch(c), c.loop.journal, model, c.loop.journal.controls
        )
    assert c.loader.session.calls == 1


@pytest.mark.parametrize(
    "change",
    ["prompt", "parameters", "before", "attempt", "budget", "authority", "pending"],
)
def test_mismatched_public_call_or_source_denial_never_loads_model(
    tmp_path: Path, change: str
) -> None:
    c = case(tmp_path)
    request, authority, model = bound(c)
    intent = c.intent
    if change == "prompt":
        prompt = ActorPrompt.model_validate_json(c.loop.store.read(intent.input_ref))
        prompt = prompt.model_copy(
            update={
                "messages": (
                    prompt.messages[0],
                    prompt.messages[1].model_copy(
                        update={"content": "A fabricated public page"}
                    ),
                )
            }
        )
        intent = intent.model_copy(
            update={
                "input_ref": reference(
                    prompt, "actor-model-input/1", store=c.loop.store
                )
            }
        )
    elif change == "parameters":
        from lab_generate_skill.domain.actor_engine import LocalActorParameters

        params = LocalActorParameters.model_validate_json(
            c.loop.store.read(intent.parameters_ref)
        )
        intent = intent.model_copy(
            update={
                "parameters_ref": reference(
                    params.model_copy(update={"seed": params.seed + 1}),
                    "model-parameters/1",
                    store=c.loop.store,
                )
            }
        )
    elif change == "before":
        from lab_generate_skill.domain.observation import Observation

        observed = Observation.model_validate_json(
            c.loop.store.read(intent.before_observation_ref)
        )
        intent = intent.model_copy(
            update={
                "before_observation_ref": reference(
                    observed.model_copy(update={"text": "different"}),
                    "observation/1",
                    "public",
                    c.loop.store,
                )
            }
        )
    elif change == "attempt":
        changed = intent.scope.model_copy(update={"context_id": "foreign-context"})
        intent = intent.model_copy(update={"scope": changed})
    elif change == "budget":
        from datetime import timedelta

        intent = intent.model_copy(
            update={
                "operation": intent.operation.model_copy(
                    update={
                        "operation_id": "different-deadline",
                        "deadline": request.operation.deadline + timedelta(seconds=1),
                    }
                )
            }
        )
    elif change == "authority":
        c.loop.authority.denied = True
    else:
        c.loop.journal.append(
            GenerationPlanned(operation=c.event_op, intent=c.intent), 0, c.event_op
        )
    with pytest.raises((OwnershipConflict, EvidenceIntegrityError, PermissionError)):
        model.validate(intent, control=c.loop.journal.controls.bind(intent.operation))
    assert c.loader.loads == c.loader.session.calls == 0
    assert not list(c.root.iterdir())


def test_missing_pending_intent_and_invented_return_rejected(tmp_path: Path) -> None:
    c = case(tmp_path)
    _, authority, model = bound(c)
    control = c.loop.journal.controls.bind(c.intent.operation)
    with pytest.raises(OwnershipConflict, match="pending intent"):
        model.generate(c.intent, control=control)
    assert c.loader.session.calls == 0
    from lab_generate_skill.domain.actor_engine import LocalActorOutput

    assert c.client.owner_guard is not None
    execution = LocalActorExecution(
        call=LocalActorCall(binding=c.binding, intent=c.intent),
        guard=c.client.owner_guard,
        command_ref=reference({}, "actor-worker-command/1", store=c.loop.store),
        reply_ref=reference({}, "actor-worker-reply/1", store=c.loop.store),
        response_ref=reference({}, "actor-model-response/1", store=c.loop.store),
        output=LocalActorOutput(
            text="invented", finish_reason="stop", prompt_tokens=1, completion_tokens=1
        ),
    )
    with pytest.raises(OwnershipConflict, match="original trace intent"):
        authority.verify_return(execution, control)
    assert not list(c.root.iterdir())


def test_two_turn_loop_reconstructs_current_page_and_original_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = case(tmp_path)
    request, authority, model = bound(c)
    completed: list[LocalActorExecution] = []
    verify = authority.verify_return

    def observed(execution: LocalActorExecution, control: OperationControl) -> None:
        verify(execution, control)
        completed.append(execution)

    monkeypatch.setattr(authority, "verify_return", observed)
    original = c.loader.session.infer

    def infer(*args: Any) -> LocalActorOutput:
        if c.loader.session.calls == 1:
            c.loader.session.output = c.loader.session.output.model_copy(
                update={"text": '{"action":"send_msg_to_user(\'Saved\')"}'}
            )
        return original(*args)

    monkeypatch.setattr(c.loader.session, "infer", infer)
    deps = replace(c.loop.runner.deps, model=model)
    result = RecordedActorRunner(deps).run(request)
    assert result.project().sealed is not None
    assert c.loader.session.calls == c.loop.browser.calls == len(completed) == 2
    # Each historical return reconstructs its own prefix, even after later
    # actions and sealing; live source denial does not erase actual facts.
    c.loop.authority.denied = True
    for execution in completed:
        verify(execution, c.loop.journal.controls.bind(request.operation))
    first, second = [
        ActorPrompt.model_validate_json(c.loop.store.read(e.call.intent.input_ref))
        for e in completed
    ]
    assert first != second and "Saved public state" in second.messages[1].content
    assert "click" in second.messages[1].content
