"""Verify retained Actor command/reply/response against the original call.

Content consistency is not source admission or proof of live execution. The
caller must additionally verify the original acquisition and business authority.
"""

import hashlib
from lab_generate_skill.domain.local_actor import LocalActorExecution
from lab_generate_skill.domain.actor_prompt import ActorPrompt, MAX_ACTOR_INPUT_BYTES
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.actor_response import ActorTextCompletion
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from .local_actor_evidence import ActorEvidence
from .actor_worker_protocol import (
    decode_command,
    decode_reply,
    validate_worker_output,
    MAX_WORKER_PACKET,
)


def verify_execution(
    evidence: ActorEvidence,
    execution: LocalActorExecution,
    control: OperationControl,
    *,
    inputs: ActorEvidence | None = None,
) -> None:
    execution = LocalActorExecution.model_validate(execution)
    call = execution.call
    intent = call.intent
    original_inputs = evidence if inputs is None else inputs
    prompt = original_inputs.read(
        intent.input_ref,
        "actor-model-input/1",
        ActorPrompt,
        MAX_ACTOR_INPUT_BYTES,
        control,
    )
    params = original_inputs.read(
        intent.parameters_ref,
        "model-parameters/1",
        LocalActorParameters,
        16384,
        control,
    )
    command = decode_command(
        evidence.raw(execution.command_ref, MAX_WORKER_PACKET, control)
    )
    reply = decode_reply(
        command, evidence.raw(execution.reply_ref, MAX_WORKER_PACKET, control)
    )
    if (
        command.operation != "generate"
        or command.session_id != call.binding.resource.expected_resource_id
        or command.request != prompt
        or command.parameters != params
        or reply.status != "ok"
        or reply.output is None
    ):
        raise EvidenceIntegrityError("Actor execution differs from original invocation")
    output = validate_worker_output(reply.output, params)
    completion = evidence.read(
        execution.response_ref,
        "actor-model-response/1",
        ActorTextCompletion,
        MAX_WORKER_PACKET,
        control,
    )
    expected = ActorTextCompletion(
        generation_id=intent.generation_id,
        request_id=intent.request_id,
        input_ref=intent.input_ref,
        parameters_ref=intent.parameters_ref,
        model_input_sha256=hashlib.sha256(prompt.input_bytes()).hexdigest(),
        text=output.text,
        finish_reason=output.finish_reason,
    )
    if execution.output != output or completion != expected:
        raise EvidenceIntegrityError(
            "Actor completion differs from original wire return"
        )
    control.checkpoint()
