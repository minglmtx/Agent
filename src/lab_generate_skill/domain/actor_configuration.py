"""Pure Actor byte/schema joins shared by configuration and release consumers.

Only supplied immutable data is inspected. No store, allocation, owner, claim,
filesystem or model is consulted, and success is never a resource permission.
The caller still verifies the actual release, files, source and live authority.
"""

import hashlib
from .actor_engine import ActorEngineConfig, LocalActorParameters
from .actor_model_binding import ActorModelBinding
from .errors import OwnershipConflict
from .evidence import EvidenceRef
from .release import ReleaseArtifact
from .state_scope import private_state_ref
from .validation import Contract


def _document(value: Contract, reference: EvidenceRef, schema: str) -> None:
    reference = EvidenceRef.model_validate(reference)
    private_state_ref(reference, schema)
    raw = value.model_dump_json().encode()
    if (
        reference.media_type != "application/json"
        or reference.sha256 != hashlib.sha256(raw).hexdigest()
        or reference.size_bytes != len(raw)
    ):
        raise OwnershipConflict("Actor configuration differs from its original bytes")


def check_actor_model_configuration(
    artifact: ReleaseArtifact,
    config: ActorEngineConfig,
    binding: ActorModelBinding,
    routing_ref: EvidenceRef,
) -> None:
    """Check transport envelope and canonical bodies without inventing an owner."""
    artifact = ReleaseArtifact.model_validate(artifact)
    config = ActorEngineConfig.model_validate(config)
    binding = ActorModelBinding.model_validate(binding)
    # The body is actor-model-binding/1; its existing transport envelope is
    # model-binding/1. These identifiers deliberately have different meanings.
    _document(binding, routing_ref, "model-binding/1")
    _document(config, binding.engine_config_ref, config.schema_version)
    if binding.model_artifact_id != artifact.artifact_id:
        raise OwnershipConflict(
            "Actor configuration changed the original model artifact"
        )


def check_actor_parameter_configuration(
    config: ActorEngineConfig,
    parameters: LocalActorParameters,
    parameters_ref: EvidenceRef,
) -> None:
    """Check the original reserve and parameter bytes; no counting or inference."""
    config = ActorEngineConfig.model_validate(config)
    parameters = LocalActorParameters.model_validate(parameters)
    config.check_output_reserve(parameters.max_new_tokens)
    _document(parameters, parameters_ref, "model-parameters/1")
