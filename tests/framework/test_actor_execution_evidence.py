"""Retained exchanges must bind exact original inputs, parameters and response."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.models.actor_execution_evidence import verify_execution
from lab_generate_skill.adapters.models.local_actor_evidence import ActorEvidence
from lab_generate_skill.application.actor_generation import execute_actor_generation
from lab_generate_skill.domain.actor_response import ActorTextCompletion
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from local_actor_fixtures import case
from test_local_actor import dispatch
from retrieval_fixtures import reference


@pytest.mark.parametrize(
    "change", ["none", "output", "response", "input", "parameters", "reply", "oversize"]
)
def test_original_exchange_rejects_substituted_facts(
    tmp_path: Path, change: str
) -> None:
    c = case(tmp_path)
    execute_actor_generation(
        dispatch(c), c.loop.journal, c.model, c.loop.journal.controls
    )
    execution = c.authority.completed[0]
    evidence = ActorEvidence(c.loop.store)
    control = c.loop.journal.controls.bind(c.intent.operation)
    if change == "none":
        verify_execution(evidence, execution, control)
        return
    if change == "output":
        execution = execution.model_copy(
            update={"output": execution.output.model_copy(update={"text": "invented"})}
        )
    elif change == "response":
        completion = ActorTextCompletion.model_validate_json(
            c.loop.store.read(execution.response_ref)
        )
        execution = execution.model_copy(
            update={
                "response_ref": reference(
                    completion.model_copy(update={"text": "invented"}),
                    "actor-model-response/1",
                    store=c.loop.store,
                )
            }
        )
    elif change in ("input", "parameters"):
        from lab_generate_skill.domain.actor_prompt import ActorPrompt
        from lab_generate_skill.domain.actor_engine import LocalActorParameters

        if change == "input":
            prompt = ActorPrompt.model_validate_json(
                c.loop.store.read(c.intent.input_ref)
            )
            prompt = prompt.model_copy(
                update={
                    "messages": (
                        prompt.messages[0],
                        prompt.messages[1].model_copy(
                            update={"content": "Another public page"}
                        ),
                    )
                }
            )
            intent = c.intent.model_copy(
                update={
                    "input_ref": reference(
                        prompt, "actor-model-input/1", store=c.loop.store
                    )
                }
            )
        else:
            params = LocalActorParameters.model_validate_json(
                c.loop.store.read(c.intent.parameters_ref)
            )
            intent = c.intent.model_copy(
                update={
                    "parameters_ref": reference(
                        params.model_copy(update={"seed": params.seed + 1}),
                        "model-parameters/1",
                        store=c.loop.store,
                    )
                }
            )
        execution = execution.model_copy(
            update={"call": execution.call.model_copy(update={"intent": intent})}
        )
    elif change == "reply":
        from lab_generate_skill.adapters.models.actor_worker_protocol import (
            decode_command,
            decode_reply,
        )

        command = decode_command(c.loop.store.read(execution.command_ref))
        reply = decode_reply(command, c.loop.store.read(execution.reply_ref))
        execution = execution.model_copy(
            update={
                "reply_ref": reference(
                    reply.model_copy(update={"command_sha256": "f" * 64}),
                    "actor-worker-reply/1",
                    store=c.loop.store,
                )
            }
        )
    else:
        execution = execution.model_copy(
            update={
                "command_ref": execution.command_ref.model_copy(
                    update={"size_bytes": 17 * 1024 * 1024}
                )
            }
        )
    with pytest.raises((EvidenceIntegrityError, ValueError)):
        verify_execution(evidence, execution, control)
