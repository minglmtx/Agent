"""Resident Generator interface over shared immutable model/process ownership.

Generator wire, request/parameter binding and token budget semantics are unchanged.
External supervision and durable original-call admission remain required.
"""

from pathlib import Path
from lab_generate_skill.domain.generator_engine import GeneratorEngineConfig
from lab_generate_skill.domain.generator_model import GeneratorModelRequest
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorParameters,
    LocalGeneratorOutput,
)
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OwnershipConflict,
    GeneratorInputBudgetExceeded,
)
from lab_generate_skill.domain.release import ReleaseArtifact
from lab_generate_skill.ports.lifecycle import OperationControl
from .generator_session import GeneratorSession, GeneratorSessionLoader
from .transformers_session import TransformersGeneratorSession
from .resident_state import ResidentState


class ResidentGeneratorEngine(ResidentState[GeneratorSession]):
    def __init__(
        self,
        artifact: ReleaseArtifact,
        config: GeneratorEngineConfig,
        *,
        loader: GeneratorSessionLoader = TransformersGeneratorSession,
    ) -> None:
        self._config = GeneratorEngineConfig.model_validate(config)
        super().__init__(
            artifact,
            self._config.packages,
            lambda: loader(Path(self.artifact.root), self._config),
        )

    @property
    def config(self) -> GeneratorEngineConfig:
        return self._config

    def _tokens(
        self,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> tuple[int, ...]:
        session = self._load(control)
        try:
            tokens = session.tokenize(request, parameters)
            control.checkpoint()
            if (
                type(tokens) is not tuple
                or not tokens
                or any(type(t) is not int or t < 0 for t in tokens)
            ):
                raise EvidenceIntegrityError(
                    "Generator session returned invalid token IDs"
                )
        except BaseException as error:
            self._failed(error)
            raise
        if (
            len(tokens) > parameters.max_input_tokens
            or len(tokens) + parameters.max_new_tokens > self.config.context_window
        ):
            raise GeneratorInputBudgetExceeded(
                "Generator input plus reserved output exceeds frozen token budget; no truncation"
            )
        return tokens

    def _inputs(
        self, request: GeneratorModelRequest, parameters: LocalGeneratorParameters
    ) -> tuple[GeneratorModelRequest, LocalGeneratorParameters]:
        request = GeneratorModelRequest.model_validate(request)
        parameters = LocalGeneratorParameters.model_validate(parameters)
        if (request.seed, request.temperature) != (
            parameters.seed,
            parameters.temperature,
        ):
            raise OwnershipConflict(
                "Generator request differs from actual sampling parameters"
            )
        return request, parameters

    def validate(
        self,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> None:
        request, parameters = self._inputs(request, parameters)
        with self._held(control):
            self._tokens(request, parameters, control)
            control.checkpoint()

    def generate(
        self,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> LocalGeneratorOutput:
        request, parameters = self._inputs(request, parameters)
        with self._held(control):
            tokens = self._tokens(request, parameters, control)
            assert self._session is not None
            try:
                control.checkpoint()
                output = LocalGeneratorOutput.model_validate(
                    self._session.infer(tokens, parameters, control)
                )
                control.checkpoint()
                if (
                    output.prompt_tokens != len(tokens)
                    or not 1 <= output.completion_tokens <= parameters.max_new_tokens
                    or output.finish_reason not in ("stop", "length")
                ):
                    raise EvidenceIntegrityError(
                        "Generator output does not match actual token invocation"
                    )
                return output
            except BaseException as error:
                self._failed(error)
                raise
