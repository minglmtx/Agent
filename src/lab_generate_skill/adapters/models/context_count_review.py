"""Independent closed read of original native count frames; no worker/model I/O."""

import hashlib
from typing import TypeVar
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.actor_context_count import (
    ActorCountExecution,
    digest,
)
from lab_generate_skill.domain.actor_engine import (
    ActorEngineConfig,
    LocalActorParameters,
)
from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
from lab_generate_skill.domain.context_budget import (
    ContextBudgetProfile,
    CountedContextInput,
    TokenMeasurement,
)
from lab_generate_skill.domain.context_projection import ContextProjectionPolicy
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.release import ReleaseArtifact
from lab_generate_skill.domain.release_installation import InstalledReleaseSources
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.wire_json import json_object
from .actor_count_protocol import (
    ActorCountCommand,
    decode_worker_command,
    decode_count_reply,
)
from .actor_worker_protocol import MAX_WORKER_PACKET
from .context_tokens import actor_budget_profile

T = TypeVar("T", bound=Contract)


def _raw(
    store: EvidenceReader,
    ref: EvidenceRef,
    schema: str,
    limit: int,
    control: OperationControl,
) -> bytes:
    if (ref.visibility, ref.content_schema, ref.media_type) != (
        "private",
        schema,
        "application/json",
    ) or not 0 < ref.size_bytes <= limit:
        raise EvidenceIntegrityError("Original bounded private count evidence required")
    control.checkpoint()
    raw = store.read(ref, control)
    if type(raw) is not bytes or (len(raw), hashlib.sha256(raw).hexdigest()) != (
        ref.size_bytes,
        ref.sha256,
    ):
        raise EvidenceIntegrityError("Original count evidence bytes changed")
    control.checkpoint()
    return raw


def _document(
    store: EvidenceReader,
    ref: EvidenceRef,
    schema: str,
    model: type[T],
    control: OperationControl,
) -> T:
    raw = _raw(store, ref, schema, 256 * 1024, control)
    json_object(raw)
    value = model.model_validate_json(raw)
    if value.model_dump_json().encode() != raw:
        raise EvidenceIntegrityError("Count evidence must retain canonical bytes")
    return value


class ActorContextCountReviewer:
    def __init__(
        self,
        evidence: EvidenceReader,
        profile: ContextBudgetProfile,
        binding: ActorModelBinding,
        parameters: LocalActorParameters,
        artifact: ReleaseArtifact,
        config: ActorEngineConfig,
        *,
        session_id: str,
        guard: ProcessOwnerGuard,
        installed_sources: InstalledReleaseSources,
    ) -> None:
        profile = ContextBudgetProfile.model_validate(profile)
        expected = actor_budget_profile(
            artifact,
            config,
            binding,
            profile.routing_ref,
            parameters,
            profile.configuration_ref,
            soft_target=profile.soft_target,
        )
        if profile != expected:
            raise OwnershipConflict(
                "Reviewer requires original frozen Actor count profile"
            )
        self._evidence, self._profile = evidence, profile
        self._artifact = ReleaseArtifact.model_validate(artifact)
        self._config = ActorEngineConfig.model_validate(config)
        self._parameters = LocalActorParameters.model_validate(parameters)
        self._session = session_id
        self._guard = ProcessOwnerGuard.model_validate(guard)
        self._installed = InstalledReleaseSources.model_validate(installed_sources)

    def verify(
        self,
        counted: CountedContextInput,
        profile: ContextBudgetProfile,
        policy: ContextProjectionPolicy,
        *,
        control: OperationControl,
    ) -> TokenMeasurement:
        counted = CountedContextInput.model_validate(counted)
        profile = ContextBudgetProfile.model_validate(profile)
        policy = ContextProjectionPolicy.model_validate(policy)
        measurement = counted.measurement
        if (
            profile != self._profile
            or policy.role != "actor"
            or (
                measurement.profile_sha256,
                measurement.policy_sha256,
                measurement.role,
                measurement.precision,
            )
            != (profile.digest, policy.digest, "actor", "exact")
        ):
            raise OwnershipConflict("Count review changed original profile/policy/role")
        execution = _document(
            self._evidence,
            counted.evidence_ref,
            "actor-context-count-execution/1",
            ActorCountExecution,
            control,
        )
        if (
            execution.measurement != measurement
            or execution.guard != self._guard
            or execution.installed_sources != self._installed
        ):
            raise EvidenceIntegrityError(
                "Count execution differs from original measurement/worker/installation"
            )
        command_raw = _raw(
            self._evidence,
            execution.command_ref,
            "actor-context-count-command/1",
            MAX_WORKER_PACKET,
            control,
        )
        command = decode_worker_command(command_raw)
        if (
            not isinstance(command, ActorCountCommand)
            or command.session_id != self._session
            or command.parameters != self._parameters
        ):
            raise OwnershipConflict(
                "Count command differs from original session/parameters"
            )
        reply = decode_count_reply(
            command,
            _raw(
                self._evidence,
                execution.reply_ref,
                "actor-context-count-reply/1",
                MAX_WORKER_PACKET,
                control,
            ),
        )
        if reply.status != "ok" or reply.measurement is None:
            raise EvidenceIntegrityError("Original successful native count required")
        native = reply.measurement
        native.verify(command.request, command.parameters, self._artifact, self._config)
        input_raw = _raw(
            self._evidence,
            measurement.input_ref,
            "actor-model-input/1",
            8 * 1024**2,
            control,
        )
        if (
            command.request.model_dump_json().encode() != input_raw
            or native.input_sha256 != digest(command.request)
            or native.input_tokens != measurement.input_tokens
            or measurement.input_tokens != measurement.upper_bound_tokens
            or native.observation_tokens != measurement.observation_tokens
            or native.observation_body_sha256 != measurement.observation_body_sha256
        ):
            raise EvidenceIntegrityError(
                "Count differs from complete original input or native return"
            )
        control.checkpoint()
        return measurement
