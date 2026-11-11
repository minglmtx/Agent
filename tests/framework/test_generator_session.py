"""Chat-template/tokenization call shape with a deliberate unit tokenizer."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.models.transformers_session import (
    TransformersGeneratorSession,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from generator_engine_fixtures import setup


class Tokenizer:
    def __init__(self) -> None:
        self.template: dict[str, Any] = {}
        self.encoding: dict[str, Any] = {}
        self.ids: object = [1, 2, 3]
        self.error: Exception | None = None

    def apply_chat_template(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        self.template = kwargs
        if self.error is not None:
            raise self.error
        return "exact rendered 任务"

    def __call__(self, text: str, **kwargs: Any) -> dict[str, object]:
        assert text == "exact rendered 任务"
        self.encoding = kwargs
        return {"input_ids": self.ids}


def test_no_hidden_truncation_or_template_fallback(tmp_path: Path) -> None:
    _, _, request, parameters, _ = setup(tmp_path)
    session = object.__new__(TransformersGeneratorSession)
    tokenizer = Tokenizer()
    session._model = object()
    session._tokenizer = tokenizer
    assert session.tokenize(request, parameters) == (1, 2, 3)
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
        session.tokenize(request, parameters)
    assert caught.value is error


@pytest.mark.parametrize("ids", [[], [True], [-1], ["1"], None, (1, 2)])
def test_tokenizer_invalid_output_is_rejected(tmp_path: Path, ids: object) -> None:
    _, _, request, parameters, _ = setup(tmp_path)
    session = object.__new__(TransformersGeneratorSession)
    session._model = object()
    tokenizer = Tokenizer()
    tokenizer.ids = ids
    session._tokenizer = tokenizer
    with pytest.raises(EvidenceIntegrityError):
        session.tokenize(request, parameters)
