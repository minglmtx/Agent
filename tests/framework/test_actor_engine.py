"""Role separation, bounded inference and irreversible failure ownership."""

import os
from pathlib import Path
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.models.transformers_actor import ResidentActorEngine
from lab_generate_skill.domain.actor_engine import (
    ActorEngineConfig,
    LocalActorParameters,
)
from lab_generate_skill.domain.errors import (
    ActorInputBudgetExceeded,
    EvidenceIntegrityError,
    OwnershipConflict,
    OperationStopped,
)
from actor_engine_fixtures import setup, config


def test_preflight_reuse_and_close(tmp_path: Path) -> None:
    engine, loader, request, parameters, control = setup(tmp_path)
    engine.validate(request, parameters, control)
    assert loader.loads == 1 and loader.session.calls == 0
    assert engine.generate(request, parameters, control) == loader.session.output
    assert (
        engine.generate(request, parameters, control).schema_version
        == "actor-engine-output/1"
    )
    assert loader.loads == 1 and loader.session.calls == 2
    engine.close(control)
    engine.close(control)
    assert loader.session.closed == 1
    with pytest.raises(OwnershipConflict):
        engine.generate(request, parameters, control)


@pytest.mark.parametrize(
    "field,value",
    [
        ("model_type", "qwen3"),
        ("schema_version", "generator-engine-config/1"),
        ("dtype", "auto"),
        ("device", "cpu"),
        ("cpu_threads", True),
        ("context_window", 0),
        ("packages", ()),
        ("extra", 1),
    ],
)
def test_actor_config_rejects_wrong_role_and_implicit_runtime(
    field: str, value: object
) -> None:
    data = config().model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        ActorEngineConfig.model_validate(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_input_tokens", 0),
        ("max_new_tokens", True),
        ("max_new_tokens", 65537),
        ("seed", -1),
        ("temperature", float("nan")),
        ("top_p", 0),
        ("top_p", float("inf")),
        ("enable_thinking", True),
        ("enable_thinking", 0),
        ("schema_version", "local-generator-parameters/1"),
    ],
)
def test_actor_sampling_rejects_illegal_input(
    tmp_path: Path, field: str, value: object
) -> None:
    _, _, _, params, _ = setup(tmp_path)
    data = params.model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        LocalActorParameters.model_validate(data)


@pytest.mark.parametrize("budget", ["input", "combined"])
def test_exact_boundary_and_no_truncation(tmp_path: Path, budget: str) -> None:
    engine, loader, request, params, control = setup(tmp_path)
    short = params.model_copy(
        update={"max_input_tokens": 2} if budget == "input" else {"max_new_tokens": 198}
    )
    with pytest.raises(ActorInputBudgetExceeded):
        engine.validate(request, short, control)
    assert loader.session.calls == loader.session.closed == 0
    exact = params.model_copy(update={"max_input_tokens": 3, "max_new_tokens": 197})
    assert engine.generate(request, exact, control).prompt_tokens == 3
    assert loader.loads == 1
    engine.close(control)


@pytest.mark.parametrize("fault", ["root_writable", "damaged", "version"])
def test_wrong_assets_never_load(tmp_path: Path, fault: str) -> None:
    engine, loader, request, params, control = setup(tmp_path)
    root = Path(engine.artifact.root)
    if fault == "root_writable":
        root.chmod(0o755)
    elif fault == "damaged":
        path = root / "config.json"
        path.chmod(0o644)
        path.write_bytes(b"tampered")
        path.chmod(0o444)
    else:
        pins = engine.config.packages
        wrong = engine.config.model_copy(
            update={
                "packages": (pins[0].model_copy(update={"version": "0"}), *pins[1:])
            }
        )
        engine = ResidentActorEngine(engine.artifact, wrong, loader=loader)
    with pytest.raises(EvidenceIntegrityError):
        engine.validate(request, params, control)
    assert loader.loads == 0
    with pytest.raises(OwnershipConflict):
        engine.validate(request, params, control)


@pytest.mark.parametrize(
    "fault", ["prompt", "zero", "over", "finish", "engine", "stop", "cleanup"]
)
def test_failure_closes_once_and_never_reloads(tmp_path: Path, fault: str) -> None:
    engine, loader, request, params, control = setup(tmp_path)
    if fault in ("prompt", "zero", "over", "finish"):
        field, value = {
            "prompt": ("prompt_tokens", 4),
            "zero": ("completion_tokens", 0),
            "over": ("completion_tokens", 101),
            "finish": ("finish_reason", "other"),
        }[fault]
        loader.session.output = loader.session.output.model_copy(update={field: value})
    else:
        loader.session.failure = (
            OperationStopped("CANCELLED", "unit")
            if fault == "stop"
            else RuntimeError("inference failed")
        )
        if fault == "cleanup":
            loader.session.cleanup_failure = OSError("release failed")
    with pytest.raises(
        (EvidenceIntegrityError, RuntimeError, OperationStopped, BaseExceptionGroup)
    ) as caught:
        engine.generate(request, params, control)
    if fault == "cleanup":
        group = cast(BaseExceptionGroup[BaseException], caught.value)
        assert group.exceptions == (
            loader.session.failure,
            loader.session.cleanup_failure,
        )
    elif loader.session.failure is not None:
        assert caught.value is loader.session.failure
    assert loader.session.calls == loader.session.closed == 1
    with pytest.raises(OwnershipConflict):
        engine.generate(request, params, control)
    assert loader.loads == 1


@pytest.mark.parametrize("tokens", [(), (True,), (-1,)])
def test_invalid_tokens_close_before_inference(
    tmp_path: Path, tokens: tuple[int, ...]
) -> None:
    engine, loader, request, params, control = setup(tmp_path)
    loader.session.tokens = tokens
    with pytest.raises(EvidenceIntegrityError):
        engine.generate(request, params, control)
    assert loader.session.calls == 0 and loader.session.closed == 1


def test_pid_change_rejected_before_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, loader, request, params, control = setup(tmp_path)
    pid = os.getpid()
    monkeypatch.setattr(os, "getpid", lambda: pid + 1)
    with pytest.raises(OwnershipConflict):
        engine.validate(request, params, control)
    assert loader.loads == 0
