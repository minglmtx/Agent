"""Public v6 projection preserving original fields and six-skill order."""

import hashlib
import json
from lab_generate_skill.domain.construction_inputs import GenerationInput
from lab_generate_skill.domain.generator_model import (
    GeneratorMessage,
    GeneratorModelRequest,
)
from lab_generate_skill.domain.observation import ResolvedObservation
from .instructions import (
    SYSTEM,
    VIEWPORT_GUIDANCE,
    FULL_AX_GUIDANCE,
    PROMPT_VERSION,
    UNKNOWN_SCOPE_GUIDANCE,
    CAPABILITY_GUIDANCE,
    SELECTED_CAPABILITY_GUIDANCE,
    SELECTED_PROMPT_VERSION,
)
from .capabilities import actor_capabilities


def prepare_generator(
    request: GenerationInput, observation: ResolvedObservation
) -> GeneratorModelRequest:
    request = GenerationInput.model_validate(request)
    observation = ResolvedObservation.model_validate(observation)
    observation.record.check_initial(
        request.context.task.identity, request.context.context_id
    )
    text = observation.text
    if text is None or not text.strip():
        raise ValueError("Generator requires nonempty initial observation text")
    try:
        parsed = json.loads(text)
        scope = parsed.get("observation_scope") if isinstance(parsed, dict) else None
    except ValueError:
        scope = None
    guidance = (
        FULL_AX_GUIDANCE
        if scope == FULL_AX_GUIDANCE
        else VIEWPORT_GUIDANCE if scope == VIEWPORT_GUIDANCE else UNKNOWN_SCOPE_GUIDANCE
    )
    system = SYSTEM.replace(VIEWPORT_GUIDANCE, guidance)
    if request.actor_capabilities is not None:
        system = system.replace(
            guidance,
            "Initial source only; the Actor's later view follows its selected capability contract.\n"
            + guidance,
        )
        system = system.replace(CAPABILITY_GUIDANCE, SELECTED_CAPABILITY_GUIDANCE)
    user = json.dumps(
        {
            "task": request.context.task.goal,
            "initial_observation": text,
            "actor_capabilities": actor_capabilities(
                request.context.task, text, request.actor_capabilities
            ),
            "retrieved_skills": [
                skill.model_payload() for skill in request.retrieved_skills
            ],
        },
        ensure_ascii=False,
    )
    return GeneratorModelRequest(
        request_id=request.request_id,
        generation_input_sha256=hashlib.sha256(
            request.model_dump_json().encode()
        ).hexdigest(),
        prompt_version=(
            PROMPT_VERSION
            if request.actor_capabilities is None
            else SELECTED_PROMPT_VERSION
        ),
        messages=(
            GeneratorMessage(role="system", content=system),
            GeneratorMessage(role="user", content=user),
        ),
        seed=request.seed,
        temperature=request.temperature,
    )
