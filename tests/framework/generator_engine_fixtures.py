"""Small immutable model tree and explicit unit session; no GPU imports."""

from lab_generate_skill.domain.causal_model import ModelPackage

import hashlib
from pathlib import Path
from importlib.metadata import version
from lab_generate_skill.domain.release import ReleaseArtifact, ReleaseFile
from lab_generate_skill.domain.generator_engine import (
    GeneratorEngineConfig,
)
from lab_generate_skill.domain.generator_model import GeneratorModelRequest
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorParameters,
    LocalGeneratorOutput,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.models.transformers_generator import (
    ResidentGeneratorEngine,
)
from lab_generate_skill.adapters.models.generator_session import GeneratorSession
from local_generator_fixtures import case


def config() -> GeneratorEngineConfig:
    return GeneratorEngineConfig(
        dtype="bfloat16",
        cpu_threads=2,
        context_window=200,
        packages=tuple(
            ModelPackage.model_validate({"name": name, "version": version(name)})
            for name in (
                "accelerate",
                "safetensors",
                "tokenizers",
                "torch",
                "transformers",
            )
        ),
    )


def artifact(root: Path) -> ReleaseArtifact:
    root.mkdir()
    pins = []
    for name in (
        "config.json",
        "generation_config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "model.safetensors",
    ):
        raw = b"unit fixture"
        path = root / name
        path.write_bytes(raw)
        path.chmod(0o444)
        pins.append(
            ReleaseFile(
                path=name,
                sha256=hashlib.sha256(raw).hexdigest(),
                size_bytes=len(raw),
                executable=False,
            )
        )
    root.chmod(0o555)
    return ReleaseArtifact(artifact_id="unit-model", root=str(root), files=tuple(pins))


class UnitSession:
    def __init__(self) -> None:
        self.tokens: tuple[int, ...] = (1, 2, 3)
        self.calls = 0
        self.closed = 0
        self.failure: BaseException | None = None
        self.cleanup_failure: BaseException | None = None
        self.output = LocalGeneratorOutput(
            text="原输出", finish_reason="stop", prompt_tokens=3, completion_tokens=2
        )

    def tokenize(
        self, request: GeneratorModelRequest, parameters: LocalGeneratorParameters
    ) -> tuple[int, ...]:
        return self.tokens

    def infer(
        self,
        tokens: tuple[int, ...],
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> LocalGeneratorOutput:
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

    def __call__(self, root: Path, config: GeneratorEngineConfig) -> GeneratorSession:
        self.loads += 1
        return self.session


def setup(
    root: Path,
) -> tuple[
    ResidentGeneratorEngine,
    Loader,
    GeneratorModelRequest,
    LocalGeneratorParameters,
    OperationControl,
]:
    c = case(root)
    params = LocalGeneratorParameters(
        max_input_tokens=100,
        max_new_tokens=100,
        top_p=0.9,
        enable_thinking=False,
        seed=c.request.seed,
        temperature=c.request.temperature,
    )
    loader = Loader()
    engine = ResidentGeneratorEngine(artifact(root / "model"), config(), loader=loader)
    return engine, loader, c.request, params, c.controls.bind(c.operation)
