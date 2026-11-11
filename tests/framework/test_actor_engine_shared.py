"""Actor tokenization and cross-role RNG exclusion over shared model mechanics."""

from pathlib import Path
import threading
from typing import Any
import pytest
from lab_generate_skill.adapters.models.transformers_actor_session import (
    TransformersActorSession,
)
from lab_generate_skill.domain.actor_engine import LocalActorOutput
from lab_generate_skill.domain.errors import OperationStopped
from actor_engine_fixtures import setup
from generator_engine_fixtures import setup as generator_setup
from test_generator_session import Tokenizer
from test_slurm_commands import guard


def test_actor_template_has_no_fallback_or_truncation(tmp_path: Path) -> None:
    _, _, request, params, _ = setup(tmp_path)
    session = object.__new__(TransformersActorSession)
    tokenizer = Tokenizer()
    session._model, session._tokenizer = object(), tokenizer
    assert session.tokenize(request, params) == (1, 2, 3)
    assert tokenizer.template == {
        "tokenize": False,
        "add_generation_prompt": True,
        "enable_thinking": False,
    }
    assert tokenizer.encoding == {
        "truncation": False,
        "add_special_tokens": True,
        "return_attention_mask": False,
    }
    error = TypeError("unsupported template")
    tokenizer.error = error
    with pytest.raises(TypeError) as caught:
        session.tokenize(request, params)
    assert caught.value is error


def test_actor_and_generator_share_cancellable_rng_exclusion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = tmp_path / "actor", tmp_path / "generator"
    first.mkdir()
    second.mkdir()
    actor, loader, request, params, _ = setup(first)
    generator, other, generator_request, generator_params, _ = generator_setup(second)
    entered, release = threading.Event(), threading.Event()
    errors: list[BaseException] = []
    original = loader.session.infer

    def blocking(*args: Any) -> LocalActorOutput:
        entered.set()
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(loader.session, "infer", blocking)

    def run() -> None:
        try:
            actor.generate(request, params, guard(15))
        except BaseException as error:
            errors.append(error)

    worker = threading.Thread(target=run)
    worker.start()
    try:
        assert entered.wait(5)
        with pytest.raises(OperationStopped):
            generator.validate(generator_request, generator_params, guard(0.05))
        assert other.loads == 0
    finally:
        release.set()
        worker.join(10)
    assert not worker.is_alive() and not errors
    assert (
        generator.generate(generator_request, generator_params, guard()).text
        == "原输出"
    )
    actor.close(guard())
    generator.close(guard())
