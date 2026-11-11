"""Explicit Actor session fixture; real immutable file verification, no GPU."""

from pathlib import Path
from lab_generate_skill.adapters.models.actor_session import ActorSession
from lab_generate_skill.adapters.models.transformers_actor import ResidentActorEngine
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.domain.actor_engine import (
    ActorEngineConfig,
    LocalActorParameters,
    LocalActorOutput,
)
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.ports.lifecycle import OperationControl
from generator_engine_fixtures import artifact, config as generator_config
from test_actor_protocol import turn
from test_slurm_commands import guard


def config() -> ActorEngineConfig:
    return ActorEngineConfig(
        dtype="bfloat16",
        cpu_threads=2,
        context_window=200,
        packages=generator_config().packages,
    )


class UnitSession:
    def __init__(self) -> None:
        self.tokens: tuple[int, ...] = (1, 2, 3)
        self.calls = self.closed = 0
        self.failure: BaseException | None = None
        self.cleanup_failure: BaseException | None = None
        self.output = LocalActorOutput(
            text='{"action":"click(\'2\')","thought":"Save"}',
            finish_reason="stop",
            prompt_tokens=3,
            completion_tokens=2,
        )

    def tokenize(
        self, request: ActorPrompt, parameters: LocalActorParameters
    ) -> tuple[int, ...]:
        return self.tokens

    def infer(
        self,
        tokens: tuple[int, ...],
        parameters: LocalActorParameters,
        control: OperationControl,
    ) -> LocalActorOutput:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return self.output

    def close(self) -> None:
        self.closed += 1
        if self.cleanup_failure is not None:
            raise self.cleanup_failure


class Loader:
    def __init__(self) -> None:
        self.session = UnitSession()
        self.loads = 0

    def __call__(self, root: Path, config: ActorEngineConfig) -> ActorSession:
        self.loads += 1
        return self.session


def setup(
    root: Path,
) -> tuple[
    ResidentActorEngine, Loader, ActorPrompt, LocalActorParameters, OperationControl
]:
    loader = Loader()
    engine = ResidentActorEngine(artifact(root / "model"), config(), loader=loader)
    params = LocalActorParameters(
        max_input_tokens=100, max_new_tokens=100, seed=42, temperature=0.7, top_p=0.95
    )
    return engine, loader, prepare_actor(turn()), params, guard(30)
