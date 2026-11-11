"""Actor complete-input counter over an already acquired original worker.

No process launch, inference, filesystem discovery, source permit or new ledger.
The application must verify the original task/trace and request admissibility
before preparing candidates. Teacher counting uses its own adapter/profile.
"""

import hashlib
import time
from lab_generate_skill.domain.actor_context_count import (
    tokenizer_identity,
    template_identity,
    ActorCountExecution,
)
from lab_generate_skill.domain.actor_configuration import (
    check_actor_model_configuration,
    check_actor_parameter_configuration,
)
from lab_generate_skill.domain.actor_engine import (
    ActorEngineConfig,
    LocalActorParameters,
)
from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
from lab_generate_skill.domain.actor_prompt import ActorPrompt, MAX_ACTOR_INPUT_BYTES
from lab_generate_skill.domain.context_budget import (
    ContextBudgetProfile,
    TokenMeasurement,
    CountedContextInput,
)
from lab_generate_skill.domain.context_projection import ContextProjectionPolicy
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.release import ReleaseArtifact
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.wire_json import json_object
from .actor_worker_client import SupervisedActorEngine
from .local_actor_evidence import ActorEvidence
from .actor_count_exchange import ActorCountExchange


class CountPersistenceUnconfirmed(RuntimeError):
    """Original count returned, but some CAS acknowledgements are uncertain."""

    def __init__(
        self,
        measurement: TokenMeasurement,
        exchange: ActorCountExchange,
        phase: str,
        primary: BaseException,
        retained: tuple[EvidenceRef, ...],
    ) -> None:
        self.measurement, self.exchange = measurement, exchange
        self.phase, self.primary, self.retained = phase, primary, retained
        super().__init__(
            "Original context count publication unconfirmed; no automatic recount"
        )


def actor_budget_profile(
    artifact: ReleaseArtifact,
    config: ActorEngineConfig,
    binding: ActorModelBinding,
    routing_ref: EvidenceRef,
    parameters: LocalActorParameters,
    parameters_ref: EvidenceRef,
    *,
    soft_target: int,
) -> ContextBudgetProfile:
    """Pure declaration derived from existing pins; not resource authorization."""
    artifact = ReleaseArtifact.model_validate(artifact)
    config = ActorEngineConfig.model_validate(config)
    binding = ActorModelBinding.model_validate(binding)
    parameters = LocalActorParameters.model_validate(parameters)
    check_actor_model_configuration(artifact, config, binding, routing_ref)
    check_actor_parameter_configuration(config, parameters, parameters_ref)
    return ContextBudgetProfile(
        role="actor",
        model=binding.model,
        provider="fixed-actor-worker",
        routing_ref=routing_ref,
        configuration_ref=parameters_ref,
        tokenizer_sha256=tokenizer_identity(artifact),
        template_sha256=template_identity(artifact),
        counting_method="fixed-actor-template-v1",
        precision="exact",
        bound_evidence_ref=None,
        context_window=config.context_window,
        output_reserve=parameters.max_new_tokens,
        input_limit=parameters.max_input_tokens,
        provider_input_limit=None,
        soft_target=soft_target,
        uncounted_overhead=0,
        paid=False,
        fee_scope_ref=None,
    )


class ActorContextTokenCounter:
    def __init__(
        self,
        engine: SupervisedActorEngine,
        evidence: EvidenceStore,
        profile: ContextBudgetProfile,
        binding: ActorModelBinding,
        parameters: LocalActorParameters,
        *,
        session_id: str,
    ) -> None:
        profile = ContextBudgetProfile.model_validate(profile)
        parameters = LocalActorParameters.model_validate(parameters)
        expected = actor_budget_profile(
            engine.artifact,
            engine.config,
            binding,
            profile.routing_ref,
            parameters,
            profile.configuration_ref,
            soft_target=profile.soft_target,
        )
        if expected != profile or engine.session_id != session_id:
            raise OwnershipConflict(
                "Actor counter requires its exact frozen profile/route"
            )
        self._engine, self._evidence = engine, evidence
        self._profile, self._parameters = profile, parameters

    def measure(
        self,
        input_ref: EvidenceRef,
        profile: ContextBudgetProfile,
        policy: ContextProjectionPolicy,
        *,
        control: OperationControl,
    ) -> CountedContextInput:
        return self.measure_with_return(
            input_ref, profile, policy, control=control, retention_control=control
        )

    def measure_with_return(
        self,
        input_ref: EvidenceRef,
        profile: ContextBudgetProfile,
        policy: ContextProjectionPolicy,
        *,
        control: OperationControl,
        retention_control: OperationControl,
    ) -> CountedContextInput:
        started = time.monotonic()
        profile = ContextBudgetProfile.model_validate(profile)
        policy = ContextProjectionPolicy.model_validate(policy)
        input_ref = EvidenceRef.model_validate(input_ref)
        if profile != self._profile or policy.role != "actor":
            raise OwnershipConflict("Count profile or role differs from frozen Actor")
        private_state_ref(input_ref, "actor-model-input/1")
        if (
            input_ref.media_type != "application/json"
            or not 0 < input_ref.size_bytes <= MAX_ACTOR_INPUT_BYTES
        ):
            raise EvidenceIntegrityError(
                "Actor count requires bounded complete JSON input"
            )
        guard, installed = self._engine.owner_guard, self._engine.installed_sources
        if guard is None or installed is None:
            raise OwnershipConflict(
                "Counter requires an already acquired installed worker"
            )
        control.checkpoint()
        raw = self._evidence.read(input_ref, control)
        if type(raw) is not bytes or (len(raw), hashlib.sha256(raw).hexdigest()) != (
            input_ref.size_bytes,
            input_ref.sha256,
        ):
            raise EvidenceIntegrityError(
                "Count input differs from its original reference"
            )
        json_object(raw)
        prompt = ActorPrompt.model_validate_json(raw)
        if prompt.model_dump_json().encode() != raw:
            raise EvidenceIntegrityError(
                "Count input must be canonical complete Actor input"
            )
        control.checkpoint()
        exchange = self._engine.measure_exchange(
            prompt, self._parameters, control, retention_control=retention_control
        )
        reply = exchange.decoded_reply
        assert reply.measurement is not None
        native = reply.measurement
        body_fields: dict[str, object] = {}
        if native.observation_tokens is not None:
            body_fields.update(
                schema_version="context-token-measurement/2",
                observation_tokens=native.observation_tokens,
                observation_body_sha256=native.observation_body_sha256,
            )
        measurement = TokenMeasurement.model_validate(
            dict(
                role="actor",
                input_ref=input_ref,
                profile_sha256=profile.digest,
                policy_sha256=policy.digest,
                input_tokens=native.input_tokens,
                upper_bound_tokens=native.input_tokens,
                precision="exact",
                complete_request=True,
                elapsed_seconds=time.monotonic() - started,
            )
            | body_fields
        )
        retained: list[EvidenceRef] = []
        phase = "save_command"
        publication = ActorEvidence(self._evidence)
        try:
            retention_control.checkpoint()
            command_ref = publication.put(
                exchange.command,
                "actor-context-count-command/1",
                retained,
                retention_control,
            )
            phase = "save_reply"
            reply_ref = publication.put(
                exchange.reply,
                "actor-context-count-reply/1",
                retained,
                retention_control,
            )
            phase = "save_execution"
            execution = ActorCountExecution(
                measurement=measurement,
                guard=guard,
                installed_sources=installed,
                command_ref=command_ref,
                reply_ref=reply_ref,
            )
            reference = publication.put(
                execution.model_dump_json().encode(),
                execution.schema_version,
                retained,
                retention_control,
            )
            return CountedContextInput(measurement=measurement, evidence_ref=reference)
        except BaseException as error:
            raise CountPersistenceUnconfirmed(
                measurement, exchange, phase, error, tuple(retained)
            ) from error
