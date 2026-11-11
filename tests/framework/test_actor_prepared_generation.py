"""Worker consumes one exact token preparation and never reloads/counts in its core call."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.errors import OwnershipConflict, ActorInputBudgetExceeded
from lab_generate_skill.ports.lifecycle import OperationControl
from actor_engine_fixtures import setup


def test_prepared_call_consumes_once_without_tokenization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, loader, request, parameters, control = setup(tmp_path)
    engine.validate(request, parameters, control)

    def forbidden(*args: Any) -> tuple[int, ...]:
        raise AssertionError("Core execution must not tokenize again")

    monkeypatch.setattr(loader.session, "tokenize", forbidden)
    assert (
        engine.generate_prepared(request, parameters, control) == loader.session.output
    )
    assert loader.loads == loader.session.calls == 1
    with pytest.raises(OwnershipConflict):
        engine.generate_prepared(request, parameters, control)
    assert loader.session.calls == 1
    engine.close(control)
    assert engine._prepared is None and loader.session.closed == 1


@pytest.mark.parametrize(
    "change", ["missing", "parameters", "prompt", "count", "rejected"]
)
def test_missing_or_replaced_preparation_never_infers(
    tmp_path: Path, change: str
) -> None:
    engine, loader, request, parameters, control = setup(tmp_path)
    if change != "missing":
        engine.validate(request, parameters, control)
    if change == "parameters":
        parameters = parameters.model_copy(update={"seed": parameters.seed + 1})
    elif change == "prompt":
        message = request.messages[-1].model_copy(
            update={"content": "Another public input"}
        )
        request = request.model_copy(
            update={"messages": (*request.messages[:-1], message)}
        )
    elif change == "count":
        engine.measure(request, parameters, control)
    elif change == "rejected":
        with pytest.raises(ActorInputBudgetExceeded):
            engine.validate(
                request, parameters.model_copy(update={"max_input_tokens": 1}), control
            )
    with pytest.raises(OwnershipConflict):
        engine.generate_prepared(request, parameters, control)
    assert loader.session.calls == 0 and engine._prepared is None


def test_inference_failure_consumes_original_preparation_and_closes(
    tmp_path: Path,
) -> None:
    engine, loader, request, parameters, control = setup(tmp_path)
    engine.validate(request, parameters, control)
    loader.session.failure = RuntimeError("actual model failure")
    with pytest.raises(RuntimeError, match="actual model failure"):
        engine.generate_prepared(request, parameters, control)
    assert (
        engine._prepared is None and loader.session.calls == loader.session.closed == 1
    )
    with pytest.raises(OwnershipConflict):
        engine.generate_prepared(request, parameters, control)
    assert loader.session.calls == 1


def test_legacy_direct_generation_keeps_its_input_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, loader, request, parameters, control = setup(tmp_path)
    counts = 0
    tokenize = loader.session.tokenize

    def counted(*args: Any) -> tuple[int, ...]:
        nonlocal counts
        counts += 1
        return tokenize(*args)

    monkeypatch.setattr(loader.session, "tokenize", counted)
    engine.validate(request, parameters, control)
    engine.generate(request, parameters, control)
    assert counts == 2 and loader.session.calls == 1 and engine._prepared is None
