"""Shared offline Transformers mechanics; role wrappers validate their own contracts.

External process supervision is mandatory for hard model/CUDA/I/O deadlines.
"""

import copy
import importlib
from contextlib import nullcontext
from pathlib import Path
from typing import Any
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from .causal_session import (
    CausalEngineSettings,
    CausalSampling,
    CausalOutput,
    CausalPositionOverride,
)


class CausalTransformersSession:
    def __init__(
        self,
        root: Path,
        config: CausalEngineSettings,
        *,
        position: CausalPositionOverride | None = None,
    ) -> None:
        self._torch = importlib.import_module("torch")
        transformers = importlib.import_module("transformers")
        self._model: Any = None
        self._tokenizer: Any = None
        self._config = config
        self._position = position
        torch = self._torch
        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise EvidenceIntegrityError(
                "Causal model requires exactly one allocated visible CUDA device"
            )
        torch.set_num_threads(config.cpu_threads)
        try:
            self._tokenizer = transformers.AutoTokenizer.from_pretrained(
                str(root), local_files_only=True, trust_remote_code=False
            )
            options: dict[str, Any] = {}
            if position is not None:
                original = transformers.AutoConfig.from_pretrained(
                    str(root), local_files_only=True, trust_remote_code=False
                )
                if (
                    original.model_type != config.model_type
                    or original.max_position_embeddings != position.original_window
                    or original.rope_scaling is not None
                ):
                    raise EvidenceIntegrityError(
                        "Long configuration requires its unmodified original model/position settings"
                    )
                if (
                    not position.original_window
                    < config.context_window
                    <= position.maximum_window
                ):
                    raise EvidenceIntegrityError(
                        "Long deployment window differs from explicit position configuration"
                    )
                original.rope_scaling = dict(position.rope_scaling)
                original.max_position_embeddings = position.maximum_window
                options = {
                    "config": original,
                    "attn_implementation": position.attention_backend,
                }
            self._model = transformers.AutoModelForCausalLM.from_pretrained(
                str(root),
                local_files_only=True,
                trust_remote_code=False,
                use_safetensors=True,
                torch_dtype=getattr(torch, config.dtype),
                device_map=config.device,
                **options,
            )
            if (
                self._model.config.model_type != config.model_type
                or self._model.config.max_position_embeddings < config.context_window
            ):
                raise EvidenceIntegrityError(
                    "Loaded architecture/window differs from frozen engine"
                )
            if position is None and self._model.config.rope_scaling is not None:
                raise EvidenceIntegrityError(
                    "Extended rope needs its own validated engine configuration"
                )
            if position is not None and (
                self._model.config.rope_scaling != position.rope_scaling
                or self._model.config.max_position_embeddings != position.maximum_window
                or self._model.config._attn_implementation != position.attention_backend
            ):
                raise EvidenceIntegrityError(
                    "Loaded long position/attention settings changed"
                )
            self._model.eval()
            self._generation = copy.deepcopy(self._model.generation_config)
            eos = self._generation.eos_token_id
            if type(eos) is int:
                eos = [eos]
            if (
                not isinstance(eos, list)
                or not eos
                or any(type(x) is not int or x < 0 for x in eos)
            ):
                raise EvidenceIntegrityError(
                    "Model has no valid original EOS identities"
                )
            self._eos = frozenset(eos)
            if type(self._tokenizer.eos_token_id) is not int:
                raise EvidenceIntegrityError(
                    "Causal model tokenizer requires scalar EOS padding identity"
                )
        except BaseException as primary:
            try:
                self.close()
            except BaseException as cleanup:
                raise BaseExceptionGroup(
                    "Causal model load and release failed", [primary, cleanup]
                ) from None
            raise

    def _tokenize(
        self, messages: list[dict[str, str]], enable_thinking: bool
    ) -> tuple[int, ...]:
        if self._model is None or self._tokenizer is None:
            raise EvidenceIntegrityError("Causal model session is closed")
        rendered = self._tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=enable_thinking,
        )
        if type(rendered) is not str or not rendered:
            raise EvidenceIntegrityError(
                "Causal model chat template returned no literal text"
            )
        encoded = self._tokenizer(
            rendered,
            truncation=False,
            add_special_tokens=True,
            return_attention_mask=False,
        )
        ids = encoded["input_ids"]
        if (
            not isinstance(ids, list)
            or not ids
            or any(type(x) is not int or x < 0 for x in ids)
        ):
            raise EvidenceIntegrityError("Tokenizer returned malformed input IDs")
        return tuple(ids)

    def _infer(
        self,
        tokens: tuple[int, ...],
        parameters: CausalSampling,
        control: OperationControl,
    ) -> CausalOutput:
        if self._model is None:
            raise EvidenceIntegrityError("Causal model session is closed")
        torch = self._torch
        transformers = importlib.import_module("transformers")
        control.checkpoint()

        # A plain callable conforms to the installed StoppingCriteriaList interface.
        def checkpoint(input_ids: Any, scores: Any, **kwargs: Any) -> bool:
            control.checkpoint()
            return False

        ids = torch.tensor([tokens], dtype=torch.long, device=self._config.device)
        mask = torch.ones_like(ids)
        generation = copy.deepcopy(self._generation)
        generation.max_new_tokens = parameters.max_new_tokens
        generation.do_sample = parameters.temperature > 0
        generation.pad_token_id = self._tokenizer.eos_token_id
        generation.num_beams = 1
        generation.num_return_sequences = 1
        generation.return_dict_in_generate = False
        generation.output_scores = False
        generation.use_cache = True
        if generation.do_sample:
            generation.temperature, generation.top_p = (
                parameters.temperature,
                parameters.top_p,
            )
        backend = (
            nullcontext()
            if self._position is None
            else torch.nn.attention.sdpa_kernel(
                [
                    torch.nn.attention.SDPBackend.FLASH_ATTENTION,
                    torch.nn.attention.SDPBackend.EFFICIENT_ATTENTION,
                ]
            )
        )
        with backend, torch.random.fork_rng(devices=[0]), torch.inference_mode():
            torch.manual_seed(parameters.seed)
            output = self._model.generate(
                input_ids=ids,
                attention_mask=mask,
                generation_config=generation,
                stopping_criteria=transformers.StoppingCriteriaList([checkpoint]),
            )
        control.checkpoint()
        if (
            output.ndim != 2
            or output.shape[0] != 1
            or output.shape[1] < len(tokens)
            or not torch.equal(output[0, : len(tokens)], ids[0])
        ):
            raise EvidenceIntegrityError(
                "Causal model output changed the original prompt"
            )
        generated = output[0, len(tokens) :]
        count = int(generated.shape[0])
        if count < 1 or count > parameters.max_new_tokens:
            raise EvidenceIntegrityError("Causal model returned invalid token count")
        ended = int(generated[-1]) in self._eos
        if not ended and count != parameters.max_new_tokens:
            raise EvidenceIntegrityError(
                "Causal model ended early without an original EOS"
            )
        return CausalOutput(
            text=self._tokenizer.decode(generated, skip_special_tokens=True),
            finish_reason="stop" if ended else "length",
            prompt_tokens=len(tokens),
            completion_tokens=count,
        )

    def close(self) -> None:
        self._model, self._tokenizer = None, None
        if self._torch.cuda.is_available():
            if self._position is not None:
                # Pinned torch keeps cuBLAS workspaces outside model tensors.
                # This worker owns the sole visible device; release those before
                # flushing its allocator. Standard/Generator sessions stay exact.
                try:
                    self._torch._C._cuda_clearCublasWorkspaces()
                except BaseException as primary:
                    try:
                        self._torch.cuda.empty_cache()
                    except BaseException as cleanup:
                        raise BaseExceptionGroup(
                            "Long model workspace and allocator release failed",
                            [primary, cleanup],
                        ) from None
                    raise
            self._torch.cuda.empty_cache()
