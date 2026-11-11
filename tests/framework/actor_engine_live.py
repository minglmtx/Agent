"""Actual Qwen2.5 GPU leaf on saved public page; no browser or execution permit.

Explicitly selected in Slurm. Writes engineering intent before each invocation,
preserves actual output before interpreting it, never repeats an unknown call.
"""

import hashlib
import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.models.actor_session import ActorSession
from lab_generate_skill.adapters.models.transformers_actor import ResidentActorEngine
from lab_generate_skill.adapters.models.transformers_actor_session import (
    TransformersActorSession,
)
from lab_generate_skill.adapters.releases.artifact_copy import copy_pinned_file
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.actor.response import parse_actor_action
from lab_generate_skill.domain.actor_engine import (
    ActorEngineConfig,
    LocalActorParameters,
    LocalActorOutput,
)
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn
from lab_generate_skill.domain.errors import ActorInputBudgetExceeded
from lab_generate_skill.domain.observation import Observation, ResolvedObservation
from lab_generate_skill.domain.release import ReleaseArtifact
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.runtime.lifecycle import OperationGuards
from actor_engine_fixtures import config
from generator_engine_live import staging, verify_source, W as W
from generator_model_assets import pinned_causal_model
from test_actor_protocol import turn
from test_slurm_commands import Cancel


def saved_turn() -> ActorPublicTurn:
    cas = (
        W
        / "experiments/framework-core-contracts-v1/check-4772787/tmp/pytest-of-r102bf10/pytest-0/test_registered_actual_site_an0/evidence/blobs"
    )
    observation_sha = "d76d1bfd5dd9be37d592ba80d7a5053d4d3178457827babf5d9ba276f77861bb"
    context_sha = "7ce66027ac673f3372f45761a956501c1269aba440536e948f74c76e33c72df3"
    obs_raw, context_raw = (cas / observation_sha).read_bytes(), (
        cas / context_sha
    ).read_bytes()
    assert hashlib.sha256(obs_raw).hexdigest() == observation_sha
    assert hashlib.sha256(context_raw).hexdigest() == context_sha
    context = json.loads(context_raw)
    observed = Observation.model_validate_json(obs_raw)
    assert (
        observed.sequence == 0
        and context["initial_observation_ref"]["sha256"] == observation_sha
    )
    return ActorPublicTurn(
        task=PublicTask.model_validate_json(json.dumps(context["task"])),
        skill=turn().skill,
        observation=ResolvedObservation(record=observed, text=observed.text),
        history=(),
        memory=turn().memory,
    )


def test_actual_qwen25_saved_public_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = Path(os.environ["LAB_ACTOR_SOFTWARE_RECEIPT"])
    verify_source(receipt)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setenv("TOKENIZERS_PARALLELISM", "false")
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "actor-engine-native"
    output.mkdir(exist_ok=False)

    def save(name: str, value: Any) -> None:
        with (output / name).open("x") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

    original, inventory_sha = pinned_causal_model(
        W, "models/Qwen2.5-7B-Instruct", "qwen25-original"
    )
    operation = OperationContext(
        operation_id="actor-gpu-leaf",
        run_id="run",
        owner_id="owner",
        deadline=datetime.now(timezone.utc) + timedelta(seconds=540),
    )
    controls = OperationGuards(SystemClock(), Cancel())
    control = controls.bind(operation)
    request = prepare_actor(saved_turn())
    params = LocalActorParameters(
        max_input_tokens=28672,
        max_new_tokens=4096,
        seed=42,
        temperature=0.7,
        top_p=0.95,
        enable_thinking=False,
    )
    save("input.json", request.model_dump(mode="json"))
    save("parameters.json", params.model_dump(mode="json"))
    calls = loads = 0
    sessions: list[TransformersActorSession] = []
    facts: dict[str, Any] = {
        "job_id": os.environ["SLURM_JOB_ID"],
        "node": os.uname().nodename,
        "software_receipt": str(receipt),
        "model_inventory_sha256": inventory_sha,
        "model_input_sha256": hashlib.sha256(request.input_bytes()).hexdigest(),
        "source_job": "4772787",
        "scope": "Engineering model leaf using exact saved public observation; no live browser, formal task authority, registered Actor worker or training",
        "actual_browser_actions": 0,
        "paid_calls": 0,
    }

    class CountingSession(TransformersActorSession):
        def infer(
            self,
            tokens: tuple[int, ...],
            parameters: LocalActorParameters,
            control: OperationControl,
        ) -> LocalActorOutput:
            nonlocal calls
            calls += 1
            return super().infer(tokens, parameters, control)

    def loader(root: Path, config: ActorEngineConfig) -> ActorSession:
        nonlocal loads
        loads += 1
        session = CountingSession(root, config)
        sessions.append(session)
        return session

    with staging() as local:
        began = time.monotonic()
        for member in original.files:
            (local / member.path).parent.mkdir(parents=True, exist_ok=True)
            copy_pinned_file(Path(original.root), local, member, control)
        local.chmod(0o555)
        facts["copy_seconds"] = time.monotonic() - began
        cfg = config().model_copy(update={"context_window": 32768})
        engine = ResidentActorEngine(
            ReleaseArtifact(
                artifact_id="qwen25-staged", root=str(local), files=original.files
            ),
            cfg,
            loader=loader,
        )
        facts["engine_config"] = cfg.model_dump(mode="json")
        facts["staged_root"] = str(local)
        primary: BaseException | None = None
        try:
            began = time.monotonic()
            engine.validate(request, params, control)
            facts["load_verify_seconds"] = time.monotonic() - began
            assert loads == 1 and calls == 0
            with pytest.raises(ActorInputBudgetExceeded):
                engine.validate(
                    request, params.model_copy(update={"max_input_tokens": 1}), control
                )
            assert calls == 0
            torch = sessions[0]._torch
            cpu_rng, gpu_rng = (
                torch.get_rng_state().clone(),
                torch.cuda.get_rng_state(0).clone(),
            )
            save(
                "sample-intent.json",
                {
                    "kind": "engineering_leaf_call",
                    "parameters": params.model_dump(mode="json"),
                    "model_input_sha256": facts["model_input_sha256"],
                },
            )
            began = time.monotonic()
            sampled = engine.generate(request, params, control)
            save("sample-output.json", sampled.model_dump(mode="json"))
            facts["sample_seconds"] = time.monotonic() - began
            assert torch.equal(torch.get_rng_state(), cpu_rng) and torch.equal(
                torch.cuda.get_rng_state(0), gpu_rng
            )
            facts["rng_restored"] = True
            try:
                facts["parsed_action"] = str(
                    parse_actor_action(
                        sampled.text,
                        sampled.finish_reason,
                        saved_turn().task,
                        "engineering-action",
                    )
                )
                facts["parse_status"] = "valid"
            except ValueError as error:
                facts["parse_status"] = "invalid"
                facts["parse_error"] = str(error)
            boundary_params = params.model_copy(
                update={"max_new_tokens": 1, "temperature": 0.0, "seed": 0}
            )
            save(
                "length-boundary-intent.json",
                {
                    "kind": "distinct_engineering_boundary_call",
                    "parameters": boundary_params.model_dump(mode="json"),
                    "model_input_sha256": facts["model_input_sha256"],
                },
            )
            boundary = engine.generate(request, boundary_params, control)
            save("length-boundary-output.json", boundary.model_dump(mode="json"))
            assert boundary.completion_tokens == 1 and boundary.finish_reason in (
                "length",
                "stop",
            )
            assert loads == 1 and calls == 2
            facts.update(
                loads=loads,
                actual_inferences=calls,
                input_budget_refused_before_inference=True,
                actual_output_tokens=sampled.completion_tokens,
                actual_input_tokens=sampled.prompt_tokens,
            )
            verify_source(receipt)
        except BaseException as error:
            primary = error
            facts["primary_error"] = type(error).__name__
            raise
        finally:
            try:
                cleanup = operation.cleanup(
                    "actor-engine-close", now=datetime.now(timezone.utc), seconds=30
                )
                engine.close(controls.bind(cleanup))
                facts["engine_closed"] = True
            except BaseException as error:
                facts["cleanup_error"] = type(error).__name__
                if primary is not None:
                    raise BaseExceptionGroup(
                        "Actor GPU check and close failed", [primary, error]
                    ) from None
                raise
            finally:
                save("facts.json", facts)
    save("staging-closed.json", {"removed": not local.parent.exists()})
