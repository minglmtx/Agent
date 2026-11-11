"""Resident engine boundaries and failure release; actual immutable small files."""

from lab_generate_skill.domain.causal_model import validate_causal_artifact

from pathlib import Path
import os
import subprocess
import sys
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.models.transformers_generator import (
    ResidentGeneratorEngine,
)
from lab_generate_skill.domain.generator_engine import (
    GeneratorEngineConfig,
)
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.local_generator import LocalGeneratorOutput
from generator_engine_fixtures import setup, config


def test_preflight_does_not_infer_and_compatible_calls_reuse_session(
    tmp_path: Path,
) -> None:
    engine, loader, request, parameters, control = setup(tmp_path)
    engine.validate(request, parameters, control)
    assert loader.loads == 1 and loader.session.calls == 0
    assert engine.generate(request, parameters, control).text == "原输出"
    assert engine.generate(request, parameters, control).prompt_tokens == 3
    assert loader.loads == 1 and loader.session.calls == 2
    engine.close(control)
    engine.close(control)
    assert loader.session.closed == 1
    with pytest.raises(OwnershipConflict):
        engine.generate(request, parameters, control)


@pytest.mark.parametrize(
    "field,value",
    [
        ("cpu_threads", 0),
        ("cpu_threads", True),
        ("cpu_threads", 65),
        ("context_window", 0),
        ("context_window", "100"),
        ("dtype", "auto"),
        ("device", "cpu"),
        ("model_type", "unknown"),
        ("packages", ()),
        ("extra", 1),
    ],
)
def test_frozen_config_rejects_illegal_or_missing_values(
    field: str, value: object
) -> None:
    data = config().model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        GeneratorEngineConfig.model_validate(data)


@pytest.mark.parametrize("budget", ["input", "combined"])
def test_no_truncation_and_rejected_budget_does_not_destroy_healthy_model(
    tmp_path: Path, budget: str
) -> None:
    engine, loader, request, parameters, control = setup(tmp_path)
    if budget == "input":
        short = parameters.model_copy(update={"max_input_tokens": 2})
    else:
        short = parameters.model_copy(update={"max_new_tokens": 198})
    with pytest.raises(ValueError, match="no truncation"):
        engine.validate(request, short, control)
    assert loader.session.calls == 0 and loader.session.closed == 0
    exact = parameters.model_copy(update={"max_input_tokens": 3, "max_new_tokens": 197})
    engine.validate(request, exact, control)
    assert engine.generate(request, exact, control).prompt_tokens == 3
    assert loader.loads == 1


@pytest.mark.parametrize(
    "fault",
    [
        "seed",
        "temperature",
        "root_writable",
        "file_writable",
        "extra_file",
        "damaged",
        "version",
    ],
)
def test_bad_binding_and_assets_never_load_or_infer(tmp_path: Path, fault: str) -> None:
    engine, loader, request, parameters, control = setup(tmp_path)
    root = Path(engine.artifact.root)
    if fault in ("seed", "temperature"):
        parameters = parameters.model_copy(
            update={fault: 4 if fault == "seed" else 0.2}
        )
    elif fault == "root_writable":
        root.chmod(0o755)
    elif fault == "file_writable":
        (root / "config.json").chmod(0o644)
    elif fault == "extra_file":
        root.chmod(0o755)
        (root / "extra").write_bytes(b"x")
        root.chmod(0o555)
    elif fault == "damaged":
        file = root / "config.json"
        file.chmod(0o644)
        file.write_bytes(b"evil fixture")
        file.chmod(0o444)
    else:
        pins = engine.config.packages
        wrong = engine.config.model_copy(
            update={
                "packages": (pins[0].model_copy(update={"version": "0"}), *pins[1:])
            }
        )
        engine = ResidentGeneratorEngine(engine.artifact, wrong, loader=loader)
    with pytest.raises((OwnershipConflict, EvidenceIntegrityError)):
        engine.validate(request, parameters, control)
    assert loader.loads == loader.session.calls == 0


@pytest.mark.parametrize(
    "fault", ["prompt", "zero", "over", "finish", "engine", "stop", "cleanup"]
)
def test_failed_execution_closes_session_without_implicit_retry(
    tmp_path: Path, fault: str
) -> None:
    engine, loader, request, parameters, control = setup(tmp_path)
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
        engine.generate(request, parameters, control)
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
        engine.generate(request, parameters, control)
    assert loader.loads == 1


@pytest.mark.parametrize("tokens", [(), (True,), (-1,)])
def test_invalid_tokenization_closes_without_inference(
    tmp_path: Path, tokens: tuple[int, ...]
) -> None:
    engine, loader, request, parameters, control = setup(tmp_path)
    loader.session.tokens = tokens
    with pytest.raises(EvidenceIntegrityError):
        engine.validate(request, parameters, control)
    assert loader.session.calls == 0 and loader.session.closed == 1


def test_config_is_readonly_and_pid_change_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, loader, request, parameters, control = setup(tmp_path)
    with pytest.raises(AttributeError):
        setattr(engine, "config", config())
    pid = os.getpid()
    monkeypatch.setattr(os, "getpid", lambda: pid + 1)
    with pytest.raises(OwnershipConflict):
        engine.generate(request, parameters, control)
    assert loader.loads == 0


def test_import_does_not_load_heavy_runtime() -> None:
    subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            "import sys; from lab_generate_skill.adapters.models.transformers_generator import ResidentGeneratorEngine; assert 'torch' not in sys.modules and 'transformers' not in sys.modules",
        ],
        check=True,
    )


def test_lock_wait_can_stop_without_loading_second_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading
    from typing import Any
    from test_slurm_commands import guard

    first_root = tmp_path / "first"
    first_root.mkdir()
    second_root = tmp_path / "second"
    second_root.mkdir()
    engine, loader, request, parameters, _ = setup(first_root)
    other, second, _, _, _ = setup(second_root)
    entered = threading.Event()
    release = threading.Event()
    errors: list[BaseException] = []
    original = loader.session.infer

    def blocking(*args: Any) -> LocalGeneratorOutput:
        entered.set()
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(loader.session, "infer", blocking)

    def execute() -> None:
        try:
            engine.generate(request, parameters, guard(15))
        except BaseException as error:
            errors.append(error)

    worker = threading.Thread(target=execute)
    worker.start()
    try:
        assert entered.wait(5)
        with pytest.raises(OperationStopped):
            other.validate(request, parameters, guard(0.05))
        assert second.loads == 0
    finally:
        release.set()
        worker.join(10)
    assert not worker.is_alive() and not errors
    assert other.generate(request, parameters, guard()).text == "原输出"
    engine.close(guard())
    other.close(guard())


def test_concurrent_close_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading
    from test_slurm_commands import guard

    engine, loader, request, parameters, control = setup(tmp_path)
    engine.validate(request, parameters, control)
    entered = threading.Event()
    release = threading.Event()
    errors: list[BaseException] = []
    original = loader.session.close

    def blocking() -> None:
        entered.set()
        assert release.wait(5)
        original()

    monkeypatch.setattr(loader.session, "close", blocking)

    def close() -> None:
        try:
            engine.close(guard(10))
        except BaseException as error:
            errors.append(error)

    first = threading.Thread(target=close)
    second = threading.Thread(target=close)
    first.start()
    try:
        assert entered.wait(5)
        second.start()
    finally:
        release.set()
        first.join(10)
        if second.ident is not None:
            second.join(10)
    assert not first.is_alive() and not second.is_alive() and not errors
    assert loader.session.closed == 1
