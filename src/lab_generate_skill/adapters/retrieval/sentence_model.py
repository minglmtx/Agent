"""Lazy offline SentenceTransformer loading, confined to a CPU worker process."""

import importlib
import os
from pathlib import Path
from typing import Protocol, cast, TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray


class SentenceModel(Protocol):
    def encode(
        self,
        sentences: list[str],
        *,
        normalize_embeddings: bool,
        batch_size: int,
        show_progress_bar: bool,
    ) -> "NDArray[np.float32]": ...


class SentenceLoader(Protocol):
    def __call__(self, root: Path, threads: int) -> SentenceModel: ...


class _Factory(Protocol):
    def __call__(
        self, path: str, *, device: str, local_files_only: bool, trust_remote_code: bool
    ) -> SentenceModel: ...


def load_sentence_model(root: Path, threads: int) -> SentenceModel:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    torch = importlib.import_module("torch")
    torch.set_num_threads(threads)
    factory = cast(
        _Factory, importlib.import_module("sentence_transformers").SentenceTransformer
    )
    return factory(
        str(root), device="cpu", local_files_only=True, trust_remote_code=False
    )
