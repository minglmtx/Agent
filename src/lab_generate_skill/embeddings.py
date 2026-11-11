from __future__ import annotations

import math
import os
import re
from abc import ABC, abstractmethod
from collections import Counter
from typing import Any

import numpy as np

from .config import EmbeddingSettings, Settings


def _normalize(vectors: np.ndarray) -> np.ndarray:
    if vectors.size == 0:
        return vectors.astype(np.float32, copy=False)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return (vectors / norms).astype(np.float32, copy=False)


class Embedder(ABC):
    name: str
    model_name: str

    @abstractmethod
    def embed(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError

    def close(self) -> None:
        return None


class LocalHiddenStateEmbedder(Embedder):
    """Mean-pool normalized hidden states from the downloaded Qwen3-8B."""

    name = "local_hidden_state"

    def __init__(self, settings: EmbeddingSettings, model_name_or_path: str) -> None:
        self.settings = settings
        self.model_name = model_name_or_path
        self._model: Any = None
        self._tokenizer: Any = None
        self._torch: Any = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "Local hidden-state embedding needs torch, transformers, and accelerate. "
                "Install the project with: pip install -e '.[runtime]'"
            ) from exc
        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_name, trust_remote_code=True
        )
        model_kwargs: dict[str, Any] = {
            "device_map": self.settings.device_map,
            "trust_remote_code": True,
        }
        if self.settings.dtype == "auto":
            model_kwargs["torch_dtype"] = "auto"
        else:
            dtype = getattr(torch, self.settings.dtype, None)
            if dtype is None:
                raise ValueError(f"Unknown torch dtype: {self.settings.dtype}")
            model_kwargs["torch_dtype"] = dtype
        self._model = AutoModel.from_pretrained(self.model_name, **model_kwargs)
        self._model.eval()

    def embed(self, texts: list[str]) -> np.ndarray:
        self._load()
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        torch = self._torch
        vectors: list[np.ndarray] = []
        target_device = next(self._model.parameters()).device
        for start in range(0, len(texts), self.settings.batch_size):
            batch = texts[start : start + self.settings.batch_size]
            encoded = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=self.settings.max_length,
                return_tensors="pt",
            )
            encoded = {name: tensor.to(target_device) for name, tensor in encoded.items()}
            with torch.inference_mode():
                hidden = self._model(**encoded).last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1).to(hidden.dtype)
            pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
            vectors.append(pooled.float().cpu().numpy())
        return _normalize(np.concatenate(vectors, axis=0))

    def close(self) -> None:
        self._model = None
        self._tokenizer = None
        if self._torch is not None and self._torch.cuda.is_available():
            self._torch.cuda.empty_cache()


class SentenceTransformerEmbedder(Embedder):
    name = "sentence_transformers"

    def __init__(self, settings: EmbeddingSettings) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Install the sentence-transformer backend with: "
                "pip install -e '.[sentence-transformers]'"
            ) from exc
        self.settings = settings
        self.model_name = settings.model
        self._model = SentenceTransformer(settings.model)
        self._model.max_seq_length = settings.max_length

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        vectors = self._model.encode(
            texts,
            batch_size=self.settings.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=True,
        )
        return np.asarray(vectors, dtype=np.float32)


class OpenAIEmbedder(Embedder):
    name = "openai"

    def __init__(self, settings: EmbeddingSettings) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install the OpenAI backend with: pip install -e '.[openai]'") from exc
        api_key = os.environ.get(settings.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing API key environment variable: {settings.api_key_env}")
        self.settings = settings
        self.model_name = settings.model
        self._client = OpenAI(api_key=api_key, base_url=settings.api_base)

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.settings.batch_size):
            response = self._client.embeddings.create(
                model=self.model_name,
                input=texts[start : start + self.settings.batch_size],
            )
            vectors.extend(item.embedding for item in response.data)
        return _normalize(np.asarray(vectors, dtype=np.float32))


class TfidfEmbedder(Embedder):
    """Dependency-free word unigram/bigram embeddings for CPU tests and baselines."""

    name = "tfidf"
    model_name = "word-unigram-bigram-v1"

    @staticmethod
    def _terms(text: str) -> list[str]:
        tokens = re.findall(r"[a-z0-9_<>/-]+", text.lower())
        return tokens + [f"{left}::{right}" for left, right in zip(tokens, tokens[1:])]

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        documents = [self._terms(text) for text in texts]
        vocabulary = sorted({term for document in documents for term in document})
        term_index = {term: index for index, term in enumerate(vocabulary)}
        document_frequency = Counter(
            term for document in documents for term in set(document)
        )
        vectors = np.zeros((len(texts), len(vocabulary)), dtype=np.float32)
        for row, document in enumerate(documents):
            counts = Counter(document)
            denominator = max(len(document), 1)
            for term, count in counts.items():
                inverse_document_frequency = math.log(
                    (1 + len(documents)) / (1 + document_frequency[term])
                ) + 1.0
                vectors[row, term_index[term]] = (
                    count / denominator
                ) * inverse_document_frequency
        return _normalize(vectors)


def create_embedder(settings: Settings) -> Embedder:
    backend = settings.embedding.backend
    if backend == "local_hidden_state":
        return LocalHiddenStateEmbedder(
            settings.embedding, settings.embedding_model_path_or_name()
        )
    if backend == "sentence_transformers":
        return SentenceTransformerEmbedder(settings.embedding)
    if backend == "openai":
        return OpenAIEmbedder(settings.embedding)
    if backend == "tfidf":
        return TfidfEmbedder()
    raise ValueError(f"Unsupported embedding backend: {backend}")

