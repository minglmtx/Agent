"""Actual Qwen3 GPU/tokenizer parity and durable inference, engineering only."""

from local_generator_fixtures import EngineeringInvocationEngine

import argparse
import ast
import hashlib
import json
import os
import tempfile
import shutil
import time
import traceback
from contextlib import contextmanager
from collections.abc import Iterator, Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from datetime import datetime, timedelta, timezone
from lab_generate_skill.adapters.models.transformers_generator import (
    ResidentGeneratorEngine,
)
from lab_generate_skill.adapters.models.transformers_session import (
    TransformersGeneratorSession,
)
from lab_generate_skill.adapters.models.local_generator import DurableGeneratorInference
from lab_generate_skill.adapters.models.local_generator_evidence import local_metadata
from lab_generate_skill.adapters.models.generator_session import GeneratorSession
from lab_generate_skill.adapters.releases.artifact_copy import copy_pinned_file
from lab_generate_skill.domain.release import ReleaseArtifact, ReleaseFile
from lab_generate_skill.domain.generator_engine import GeneratorEngineConfig
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorBaseParameters,
    LocalGeneratorParameters,
    LocalGeneratorOutput,
)
from lab_generate_skill.domain.generator_model import (
    GeneratorMessage,
    GeneratorTextCompletion,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl
from generator_engine_fixtures import config
from generator_model_assets import pinned_model
from local_generator_fixtures import case

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
P = W / "code/lab-generate-skill"


def verify_source(receipt: Path, *, source_root: Path | None = None) -> None:
    root = P if source_root is None else source_root
    if not isinstance(root, Path):
        raise TypeError("Explicit frozen source root must be a Path")
    if not root.is_absolute() or root.resolve(strict=True) != root:
        raise ValueError("Canonical original frozen source root required")
    value = json.loads(receipt.read_text())
    if not value["passed"] or not value["source_stable_during_checks"]:
        raise ValueError("Software receipt must pass")
    for name, digest in value["files"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Source changed since software acceptance: " + name)


def legacy_generate(
    session: TransformersGeneratorSession,
    request: Any,
    parameters: LocalGeneratorParameters,
) -> Any:
    source = P / "src/lab_generate_skill/llm.py"
    raw = source.read_bytes()
    if (
        hashlib.sha256(raw).hexdigest()
        != "447e337834d09e308747d698070ca0a6eb18ec35dffbc5c5643cd6338afb953f"
    ):
        raise ValueError("Original comparison implementation changed")
    tree = ast.parse(raw)
    cls = next(
        n
        for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "TransformersChatBackend"
    )
    fn = next(
        n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "generate"
    )
    # Extract only the audited old method, never import the historical module.
    scope: dict[str, Any] = {"Any": Any, "GenerationResult": SimpleNamespace}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(source), "exec"), scope)
    settings = SimpleNamespace(**parameters.model_dump())
    old = SimpleNamespace(
        _load=lambda: None,
        _torch=session._torch,
        _tokenizer=session._tokenizer,
        _model=session._model,
        settings=settings,
        _render=lambda messages: session._tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=parameters.enable_thinking,
        ),
    )
    return scope["generate"](
        old, [m.model_dump() for m in request.messages], seed=request.seed
    )


@contextmanager
def staging(*, preserve_if: Callable[[], bool] | None = None) -> Iterator[Path]:
    temporary = Path(tempfile.mkdtemp(prefix="lab-generator-", dir="/tmp"))
    local = temporary / "model"
    primary: BaseException | None = None
    try:
        local.mkdir()
        yield local
    except BaseException as error:
        primary = error
        raise
    finally:
        errors: list[BaseException] = []
        preserve = preserve_if is not None and preserve_if()
        if not preserve:
            try:
                local.chmod(0o755)
            except BaseException as error:
                errors.append(error)
            try:
                shutil.rmtree(temporary)
            except BaseException as error:
                errors.append(error)
        if errors:
            raise BaseExceptionGroup(
                "Local model staging cleanup failed",
                ([primary] if primary else []) + errors,
            ) from None


def run(output: Path, receipt: Path) -> dict[str, Any]:
    verify_source(receipt)
    original, inventory_sha256 = pinned_model(W)
    source = Path(original.root)
    files = original.files
    c = case(output)
    op = OperationContext(
        operation_id="live-generate",
        run_id="run",
        owner_id="owner",
        deadline=datetime.now(timezone.utc) + timedelta(seconds=700),
    )
    control = c.controls.bind(op)
    with staging() as local:
        started = time.monotonic()
        for member in original.files:
            (local / member.path).parent.mkdir(parents=True, exist_ok=True)
            copy_pinned_file(source, local, member, control)
        local.chmod(0o555)
        copy_seconds = time.monotonic() - started
        artifact = ReleaseArtifact(
            artifact_id="qwen3-staged", root=str(local), files=files
        )
        cfg = config().model_copy(update={"context_window": 40960})
        loads = 0
        inferences = 0

        class CountingSession(TransformersGeneratorSession):
            def infer(
                self,
                tokens: tuple[int, ...],
                parameters: LocalGeneratorParameters,
                control: OperationControl,
            ) -> LocalGeneratorOutput:
                nonlocal inferences
                inferences += 1
                return super().infer(tokens, parameters, control)

        sessions: list[TransformersGeneratorSession] = []

        def loader(root: Path, config: GeneratorEngineConfig) -> GeneratorSession:
            nonlocal loads
            loads += 1
            session = CountingSession(root, config)
            sessions.append(session)
            return session

        engine = ResidentGeneratorEngine(artifact, cfg, loader=loader)
        request = c.request.model_copy(
            update={
                "messages": (
                    GeneratorMessage(
                        role="system",
                        content="Reply with exactly the requested short text.",
                    ),
                    GeneratorMessage(role="user", content="Say exactly: Hello world."),
                )
            }
        )
        params = LocalGeneratorParameters(
            max_input_tokens=512,
            max_new_tokens=16,
            top_p=0.9,
            enable_thinking=False,
            seed=request.seed,
            temperature=request.temperature,
        )
        primary: BaseException | None = None
        try:
            started = time.monotonic()
            engine.validate(request, params, control)
            load_seconds = time.monotonic() - started
            assert loads == 1
            old = legacy_generate(sessions[0], request, params)
            torch = sessions[0]._torch
            cpu_rng = torch.get_rng_state().clone()
            gpu_rng = torch.cuda.get_rng_state(0).clone()
            new = engine.generate(request, params, control)
            assert torch.equal(torch.get_rng_state(), cpu_rng)
            assert torch.equal(torch.cuda.get_rng_state(0), gpu_rng)
            assert inferences == 1
            assert (
                old.text,
                old.finish_reason,
                old.prompt_tokens,
                old.completion_tokens,
            ) == (new.text, new.finish_reason, new.prompt_tokens, new.completion_tokens)
            try:
                engine.validate(
                    request, params.model_copy(update={"max_input_tokens": 1}), control
                )
            except ValueError:
                pass
            else:
                raise AssertionError("Overflow must reject instead of truncating")
            greedy_request = request.model_copy(update={"seed": 0, "temperature": 0.0})
            greedy_params = params.model_copy(
                update={"seed": 0, "temperature": 0.0, "max_new_tokens": 1}
            )
            old_greedy = legacy_generate(sessions[0], greedy_request, greedy_params)
            greedy = engine.generate(greedy_request, greedy_params, control)
            assert (
                old_greedy.text,
                old_greedy.finish_reason,
                old_greedy.prompt_tokens,
                old_greedy.completion_tokens,
            ) == (
                greedy.text,
                greedy.finish_reason,
                greedy.prompt_tokens,
                greedy.completion_tokens,
            )
            assert greedy.completion_tokens == 1 and greedy.finish_reason == "length"
            assert inferences == 2 and loads == 1
            base = LocalGeneratorBaseParameters.model_validate(
                {
                    k: v
                    for k, v in params.model_dump().items()
                    if k not in ("schema_version", "seed", "temperature")
                }
            )
            binding = c.binding.model_copy(
                update={
                    "base_parameters_ref": c.evidence.put(
                        base.model_dump_json().encode(),
                        local_metadata("model-parameters/1"),
                    ),
                    "model_binding_ref": c.evidence.put(
                        json.dumps(
                            {
                                "engine": cfg.model_dump(mode="json"),
                                "artifact": artifact.model_dump(mode="json"),
                            },
                            sort_keys=True,
                        ).encode(),
                        local_metadata("model-binding/1"),
                    ),
                }
            )
            inference = DurableGeneratorInference(
                c.root,
                binding,
                EngineeringInvocationEngine(engine),
                c.evidence,
                c.controls,
                c.authority,
            )
            started = time.monotonic()
            response = inference.generate(request, op)
            inference_seconds = time.monotonic() - started
            calls_before_repeat = inferences
            assert calls_before_repeat == 3
            assert inference.generate(request, op) == response
            assert inferences == calls_before_repeat
            stored = GeneratorTextCompletion.model_validate_json(
                c.evidence.read(response)
            )
            assert stored.text == new.text and loads == 1
            snapshot = inference.inspect(request, op)
            assert snapshot.fact_ref is not None
            result = dict(
                passed=True,
                job_id=os.environ["SLURM_JOB_ID"],
                node=os.uname().nodename,
                software_receipt=str(receipt),
                source_inventory_sha256=inventory_sha256,
                engine_config=cfg.model_dump(mode="json"),
                staged_artifact=artifact.model_dump(mode="json"),
                copy_seconds=copy_seconds,
                load_verify_seconds=load_seconds,
                durable_inference_seconds=inference_seconds,
                loads=loads,
                old_new_parity=True,
                greedy_length_parity=True,
                greedy_output=greedy.model_dump(mode="json"),
                rng_state_restored=True,
                actual_engine_inferences=inferences,
                completed_replay_additional_inferences=inferences - calls_before_repeat,
                output=new.model_dump(mode="json"),
                response_ref=response.model_dump(mode="json"),
                fact_ref=snapshot.fact_ref.model_dump(mode="json"),
                legacy_llm_sha256=hashlib.sha256(
                    (P / "src/lab_generate_skill/llm.py").read_bytes()
                ).hexdigest(),
                scope="Actual Qwen3 GPU + original-method parity + durable local inference; explicit unit authority and synthetic public messages; no formal task or training",
            )
            verify_source(receipt)
            return result
        except BaseException as error:
            primary = error
            raise
        finally:
            try:
                cleanup = op.cleanup(
                    "close-engine", now=datetime.now(timezone.utc), seconds=30
                )
                engine.close(c.controls.bind(cleanup))
            except BaseException as error:
                if primary is not None:
                    raise BaseExceptionGroup(
                        "GPU check and engine cleanup failed", [primary, error]
                    ) from None
                raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--software", type=Path, required=True)
    args = parser.parse_args()
    job = os.environ["SLURM_JOB_ID"]
    output = W / "experiments/framework-generator-engine-v1" / ("check-" + job)
    output.mkdir(parents=True, exist_ok=False)
    try:
        result = run(output, args.software)
    except BaseException:
        (output / "traceback.txt").write_text(traceback.format_exc())
        result = dict(passed=False, job_id=job, traceback=str(output / "traceback.txt"))
    (output / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps({"passed": result["passed"], "result": str(output / "result.json")})
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
