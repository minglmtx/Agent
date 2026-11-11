from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from .config import GenerationSettings, Settings


@dataclass(frozen=True)
class GenerationResult:
    text: str
    finish_reason: str | None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    cost: float | None = None
    provider_response_id: str | None = None
    api_error_type: str | None = None
    api_error_code: int | None = None
    provider_request_id: str | None = None


def safe_identifier(value):
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,200}", value) else None


def exception_diagnostics(exc):
    """Persist types/stage only; never exception messages, URLs, headers or bodies."""
    chain, seen = [], set()
    current = exc
    while current is not None and id(current) not in seen and len(chain) < 12:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    stage, not_sent = 'unknown', False
    try:
        import httpx
        # A later read/write/protocol error always wins over a nested connect error.
        for types, label, safe in [
            ((httpx.ReadError, httpx.ReadTimeout), 'read', False),
            ((httpx.WriteError, httpx.WriteTimeout), 'write', False),
            ((httpx.RemoteProtocolError, httpx.LocalProtocolError), 'protocol', False),
            ((httpx.ConnectError, httpx.ConnectTimeout), 'connect', True),
            ((httpx.PoolTimeout,), 'pool', True),
        ]:
            if any(isinstance(item, types) for item in chain):
                stage, not_sent = label, safe
                break
    except ImportError:
        pass
    status = getattr(exc, 'status_code', None)
    if isinstance(status, int):
        stage, not_sent = 'http_response', False
    return dict(exception_chain=[re.sub(r'[^A-Za-z0-9_]', '', type(item).__name__)[:80] for item in chain],
                stage=stage, request_not_sent=not_sent,
                http_status=status if isinstance(status, int) else None,
                provider_request_id=safe_identifier(getattr(exc, 'request_id', None)))


class APIResponseError(RuntimeError):
    """Provider error or malformed success body; carries safe usage metadata."""
    def __init__(self, result):
        self.generation_result = result
        self.status_code = result.api_error_code
        super().__init__(result.api_error_type or "invalid_response")


def decode_chat_response(response):
    # OpenRouter may return an error object with HTTP 200 and choices=None.
    # Read usage BEFORE checking content, so a billed invalid response is retained.
    usage = getattr(response, "usage", None)
    def value(obj, key, default=None):
        return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)
    error = getattr(response, "error", None)
    code = value(error, "code")
    code = int(code) if isinstance(code, (int, str)) and str(code).isdigit() else None
    error_type = value(value(error, "metadata"), "error_type")
    # Inspect text only to classify; never persist provider text or request objects.
    message = str(value(error, "message", "")).lower()
    if "context" in message and any(word in message for word in ("exceed", "maximum", "length", "limit")):
        error_type = "context_length_exceeded"
    if not isinstance(error_type, str) or not re.fullmatch(r"[a-z_]{1,80}", error_type):
        error_type = "provider_error" if error else None
    response_id = getattr(response, "id", None)
    if not isinstance(response_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", response_id):
        response_id = None
    choices = getattr(response, "choices", None)
    choice = choices[0] if isinstance(choices, (list, tuple)) and choices else None
    content = value(value(choice, "message"), "content")
    if error_type is None and choice is None:
        error_type = "missing_choices"
    if error_type is None and not isinstance(content, str):
        error_type = "missing_text_content"
    result = GenerationResult(
        text=content if isinstance(content, str) else "",
        finish_reason="error" if error_type else value(choice, "finish_reason"),
        prompt_tokens=value(usage, "prompt_tokens"),
        completion_tokens=value(usage, "completion_tokens"),
        reasoning_tokens=value(value(usage, "completion_tokens_details"), "reasoning_tokens"),
        cost=value(usage, "cost"), provider_response_id=response_id,
        api_error_type=error_type, api_error_code=code,
        provider_request_id=safe_identifier(getattr(response, "_request_id", None)),
    )
    if error_type:
        raise APIResponseError(result)
    return result


class ChatBackend(ABC):
    name: str
    model_name: str

    @abstractmethod
    def generate(self, messages: list[dict[str, str]], *, seed: int) -> GenerationResult:
        raise NotImplementedError

    def close(self) -> None:
        return None


class TransformersChatBackend(ChatBackend):
    name = "transformers"

    def __init__(self, settings: GenerationSettings, model_name_or_path: str) -> None:
        self.settings = settings
        self.model_name = model_name_or_path
        self._tokenizer: Any = None
        self._model: Any = None
        self._torch: Any = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "The transformers backend needs torch, transformers, and accelerate. "
                "Install the project with: pip install -e '.[runtime]'"
            ) from exc

        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_name, trust_remote_code=True
        )
        self._tokenizer.truncation_side = "left"
        model_kwargs: dict[str, Any] = {
            "device_map": self.settings.device_map,
            "trust_remote_code": True,
        }
        if self.settings.dtype != "auto":
            dtype = getattr(torch, self.settings.dtype, None)
            if dtype is None:
                raise ValueError(f"Unknown torch dtype: {self.settings.dtype}")
            model_kwargs["torch_dtype"] = dtype
        else:
            model_kwargs["torch_dtype"] = "auto"
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_name, **model_kwargs
        )
        self._model.eval()

    def _render(self, messages: list[dict[str, str]]) -> str:
        kwargs = {
            "tokenize": False,
            "add_generation_prompt": True,
        }
        try:
            return self._tokenizer.apply_chat_template(
                messages, enable_thinking=self.settings.enable_thinking, **kwargs
            )
        except TypeError:
            return self._tokenizer.apply_chat_template(messages, **kwargs)

    def generate(self, messages: list[dict[str, str]], *, seed: int) -> GenerationResult:
        self._load()
        torch = self._torch
        tokenizer = self._tokenizer
        model = self._model
        rendered = self._render(messages)
        encoded = tokenizer(
            rendered,
            return_tensors="pt",
            truncation=True,
            max_length=self.settings.max_input_tokens,
        )
        target_device = next(model.parameters()).device
        encoded = {name: tensor.to(target_device) for name, tensor in encoded.items()}
        prompt_length = int(encoded["input_ids"].shape[-1])

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        do_sample = self.settings.temperature > 0
        generation_kwargs: dict[str, Any] = {
            "max_new_tokens": self.settings.max_new_tokens,
            "do_sample": do_sample,
            "pad_token_id": tokenizer.eos_token_id,
        }
        if do_sample:
            generation_kwargs.update(
                temperature=self.settings.temperature,
                top_p=self.settings.top_p,
            )
        if getattr(self, 'constrain_action_names', False):
            from .constrained_actions import make_action_prefix
            generation_kwargs['prefix_allowed_tokens_fn']=make_action_prefix(self)
        with torch.inference_mode():
            output = model.generate(**encoded, **generation_kwargs)
        generated_ids = output[0, prompt_length:]
        completion_tokens = int(generated_ids.shape[-1])
        text = tokenizer.decode(generated_ids, skip_special_tokens=True)
        eos_ids = tokenizer.eos_token_id
        if isinstance(eos_ids, int):
            eos_ids = {eos_ids}
        else:
            eos_ids = set(eos_ids or [])
        ended_with_eos = completion_tokens > 0 and int(generated_ids[-1]) in eos_ids
        finish_reason = (
            "stop"
            if ended_with_eos or completion_tokens < self.settings.max_new_tokens
            else "length"
        )
        return GenerationResult(
            text=text,
            finish_reason=finish_reason,
            prompt_tokens=prompt_length,
            completion_tokens=completion_tokens,
        )

    def close(self) -> None:
        self._model = None
        self._tokenizer = None
        if self._torch is not None and self._torch.cuda.is_available():
            self._torch.cuda.empty_cache()


class OpenAIChatBackend(ChatBackend):
    name = "openai"

    def __init__(self, settings: GenerationSettings) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install the OpenAI backend with: pip install -e '.[openai]'") from exc
        api_key = os.environ.get(settings.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing API key environment variable: {settings.api_key_env}")
        self.settings = settings
        self.model_name = settings.model
        self._client = OpenAI(api_key=api_key, base_url=settings.api_base, max_retries=0, timeout=180.0)

    def generate(self, messages: list[dict[str, str]], *, seed: int) -> GenerationResult:
        extra_body = {}
        if self.settings.reasoning_effort:
            extra_body["reasoning"] = {"effort": self.settings.reasoning_effort, "exclude": True}
        if self.settings.provider_max_price:
            extra_body["provider"] = {"sort": "price", "require_parameters": True,
                                      "max_price": self.settings.provider_max_price}
        kwargs = {}
        if self.settings.send_sampling_parameters:
            kwargs.update(temperature=self.settings.temperature, top_p=self.settings.top_p)
        if self.settings.structured_skill:
            from .schemas import CompactSkill
            kwargs["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "trajectory_skill", "strict": True, "schema": CompactSkill.model_json_schema()}}
        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            max_tokens=self.settings.max_new_tokens,
            seed=seed,
            extra_body=extra_body,
            **kwargs,
        )
        return decode_chat_response(response)



def create_chat_backend(settings: Settings, *, role: str = "generation") -> ChatBackend:
    if role not in {"generation", "actor", "skill_extractor"}:
        raise ValueError(f"Unsupported model role: {role}")
    config = getattr(settings, role)
    model = config.model
    if config.backend == "transformers":
        if model == "Qwen3-8B":
            model = os.fspath(settings.paths.qwen_model)
        return TransformersChatBackend(config, model)
    if config.backend == "openai":
        return OpenAIChatBackend(config)
    raise ValueError(f"Unsupported backend: {config.backend}")
