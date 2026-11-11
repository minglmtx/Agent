"""Resident Qwen2.5 Actor engine, separate from trace admission and supervision.

The registered worker owns this object. Compatible calls reuse one loaded model;
input-budget rejection does not corrupt a healthy model, while native failures
close it and forbid automatic reload. No download, retry or prompt truncation.
"""

from pathlib import Path
import hashlib
from lab_generate_skill.domain.actor_context_count import (
    ActorTokenCount,
    digest,
    tokenizer_identity,
    template_identity,
)
from lab_generate_skill.domain.actor_engine import (
    ActorEngineConfig,
    LocalActorParameters,
    LocalActorOutput,
)
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    ActorInputBudgetExceeded,
    OwnershipConflict,
)
from lab_generate_skill.domain.release import ReleaseArtifact
from lab_generate_skill.ports.lifecycle import OperationControl
from .actor_session import ActorSession, ActorSessionLoader, ActorObservationTokenizer
from .transformers_actor_session import TransformersActorSession
from .resident_state import ResidentState


class ResidentActorEngine(ResidentState[ActorSession]):
    def __init__(
        self,
        artifact: ReleaseArtifact,
        config: ActorEngineConfig,
        *,
        loader: ActorSessionLoader = TransformersActorSession,
    ) -> None:
        self._config = ActorEngineConfig.model_validate(config)
        self._prepared: (
            tuple[ActorPrompt, LocalActorParameters, tuple[int, ...]] | None
        ) = None
        super().__init__(
            artifact,
            self._config.packages,
            lambda: loader(Path(self.artifact.root), self._config),
        )

    @property
    def config(self) -> ActorEngineConfig:
        return self._config

    def _close(self) -> None:
        self._prepared = None
        super()._close()

    def _raw_tokens(
        self,
        request: ActorPrompt,
        parameters: LocalActorParameters,
        control: OperationControl,
    ) -> tuple[int, ...]:
        self.config.check_output_reserve(parameters.max_new_tokens)
        session = self._load(control)
        try:
            tokens = session.tokenize(request, parameters)
            control.checkpoint()
            if (
                type(tokens) is not tuple
                or not tokens
                or any(type(t) is not int or t < 0 for t in tokens)
            ):
                raise EvidenceIntegrityError("Actor session returned invalid token IDs")
        except BaseException as error:
            self._failed(error)
            raise
        return tokens

    def _tokens(
        self,
        request: ActorPrompt,
        parameters: LocalActorParameters,
        control: OperationControl,
    ) -> tuple[int, ...]:
        if request.prompt_version in (
            "browsergym-adaptive-count-probe-v1",
            "browsergym-adaptive-count-probe-v2",
        ):
            raise OwnershipConflict(
                "Observation token-count probe cannot be dispatched for inference"
            )
        tokens = self._raw_tokens(request, parameters, control)
        if (
            len(tokens) > parameters.max_input_tokens
            or len(tokens) + parameters.max_new_tokens > self.config.context_window
        ):
            raise ActorInputBudgetExceeded(
                "Actor input plus reserved output exceeds frozen token budget; no truncation"
            )
        observation_tokens = self._observation_tokens(request, control)
        if observation_tokens is not None:
            assert request.observation_view is not None
            limit = request.observation_view.body_token_limit
            if limit is None or observation_tokens > limit:
                raise ActorInputBudgetExceeded(
                    "Local observation body exceeds its independent frozen token budget"
                )
        return tokens

    def _observation_tokens(
        self, request: ActorPrompt, control: OperationControl
    ) -> int | None:
        view = request.observation_view
        if view is None or view.mode != "local":
            return None
        try:
            if not isinstance(self._session, ActorObservationTokenizer):
                raise EvidenceIntegrityError(
                    "Selected Actor session has no qualified observation text counter"
                )
            control.checkpoint()
            tokens = self._session.tokenize_observation(
                view.body(request.messages[1].content)
            )
            if type(tokens) is not tuple or any(
                type(token) is not int or token < 0 for token in tokens
            ):
                raise EvidenceIntegrityError(
                    "Original Actor observation counter returned invalid tokens"
                )
            control.checkpoint()
            return len(tokens)
        except BaseException as error:
            self._failed(error)
            raise

    def measure(
        self,
        request: ActorPrompt,
        parameters: LocalActorParameters,
        control: OperationControl,
    ) -> ActorTokenCount:
        """Count complete rendered template, including over-budget candidates.

        Tokenization never infers or truncates. validate/generate retain their
        mandatory hard rejection; this method supplies selection facts only.
        """
        request = ActorPrompt.model_validate(request)
        parameters = LocalActorParameters.model_validate(parameters)
        with self._held(control):
            self._prepared = None
            tokens = self._raw_tokens(request, parameters, control)
            observation_tokens = self._observation_tokens(request, control)
            fields: dict[str, object] = {}
            if observation_tokens is not None:
                assert request.observation_view is not None
                fields.update(
                    schema_version="actor-token-count/2",
                    observation_tokens=observation_tokens,
                    observation_body_sha256=request.observation_view.body_sha256,
                    observation_counting_method="fixed-actor-text-no-special-tokens-v1",
                )
            count = ActorTokenCount.model_validate(
                dict(
                    input_sha256=digest(request),
                    model_input_sha256=hashlib.sha256(
                        request.input_bytes()
                    ).hexdigest(),
                    parameters_sha256=digest(parameters),
                    artifact_sha256=digest(self.artifact),
                    engine_config_sha256=digest(self.config),
                    tokenizer_sha256=tokenizer_identity(self.artifact),
                    template_sha256=template_identity(self.artifact),
                    input_tokens=len(tokens),
                    context_window=self.config.context_window,
                )
                | fields
            )
            control.checkpoint()
            return count

    def validate(
        self,
        request: ActorPrompt,
        parameters: LocalActorParameters,
        control: OperationControl,
    ) -> None:
        request, parameters = ActorPrompt.model_validate(
            request
        ), LocalActorParameters.model_validate(parameters)
        with self._held(control):
            self._prepared = None
            tokens = self._tokens(request, parameters, control)
            control.checkpoint()
            # One bounded immutable handoff on this exact worker. This is not
            # permission, a cross-request cache, or a replacement for live gates.
            self._prepared = (request, parameters, tokens)

    def generate(
        self,
        request: ActorPrompt,
        parameters: LocalActorParameters,
        control: OperationControl,
    ) -> LocalActorOutput:
        request, parameters = ActorPrompt.model_validate(
            request
        ), LocalActorParameters.model_validate(parameters)
        with self._held(control):
            self._prepared = None
            tokens = self._tokens(request, parameters, control)
            return self._infer(tokens, parameters, control)

    def generate_prepared(
        self,
        request: ActorPrompt,
        parameters: LocalActorParameters,
        control: OperationControl,
    ) -> LocalActorOutput:
        request = ActorPrompt.model_validate(request)
        parameters = LocalActorParameters.model_validate(parameters)
        with self._held(control):
            prepared, self._prepared = self._prepared, None
            if (
                prepared is None
                or prepared[:2] != (request, parameters)
                or self._session is None
            ):
                raise OwnershipConflict(
                    "Exact original validated Actor tokens required; no reprepare"
                )
            return self._infer(prepared[2], parameters, control)

    def _infer(
        self,
        tokens: tuple[int, ...],
        parameters: LocalActorParameters,
        control: OperationControl,
    ) -> LocalActorOutput:
        assert self._session is not None
        try:
            control.checkpoint()
            output = LocalActorOutput.model_validate(
                self._session.infer(tokens, parameters, control)
            )
            control.checkpoint()
            if (
                output.prompt_tokens != len(tokens)
                or not 1 <= output.completion_tokens <= parameters.max_new_tokens
                or output.finish_reason not in ("stop", "length")
            ):
                raise EvidenceIntegrityError(
                    "Actor output does not match actual token invocation"
                )
            return output
        except BaseException as error:
            self._failed(error)
            raise
