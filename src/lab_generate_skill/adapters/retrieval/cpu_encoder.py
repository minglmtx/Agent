"""Resident CPU encoder with one exact whole-document-batch cache.

One model/config per process. Calls serialize under a deadline-aware lock; query
is always encoded separately. No arbitrary full-bank slicing or implicit retry.
Native calls are cooperative only; process supervision remains runtime's job.
"""

import hashlib
import json
import os
import threading
from pathlib import Path
from contextlib import contextmanager
from collections.abc import Iterator
from typing import TYPE_CHECKING

from lab_generate_skill.adapters.retrieval.encoder_files import verify_encoder
from lab_generate_skill.adapters.retrieval.sentence_model import (
    SentenceLoader,
    SentenceModel,
    load_sentence_model,
)
from lab_generate_skill.domain.encoding import (
    EncoderFiles,
    EncoderConfig,
    EncodedScores,
)
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray


class CpuEncoder:
    def __init__(
        self,
        root: Path,
        files: EncoderFiles,
        config: EncoderConfig,
        *,
        loader: SentenceLoader = load_sentence_model,
    ) -> None:
        self._root = root
        self._files = EncoderFiles.model_validate(files)
        self._config = EncoderConfig.model_validate(config)
        self._loader = loader
        self._model: SentenceModel | None = None
        self._documents: tuple[str, ...] | None = None
        self._vectors: NDArray[np.float32] | None = None
        self._lock = threading.Lock()
        self._pid = os.getpid()
        self._closed = False

    @property
    def root(self) -> Path:
        return self._root

    @property
    def files(self) -> EncoderFiles:
        return self._files

    @property
    def config(self) -> EncoderConfig:
        return self._config

    @contextmanager
    def _held(self, control: OperationControl) -> Iterator[None]:
        if os.getpid() != self._pid:
            raise OwnershipConflict("Encoder cannot cross process boundary")
        control.checkpoint()
        while not self._lock.acquire(blocking=False):
            control.wait(0.02)
        try:
            control.checkpoint()
            yield
        finally:
            self._lock.release()

    def close(self, control: OperationControl) -> None:
        with self._held(control):
            self._model = None
            self._documents = None
            self._vectors = None
            self._closed = True

    def score(
        self, documents: tuple[str, ...], query: str, control: OperationControl
    ) -> EncodedScores:
        if (
            type(documents) is not tuple
            or not 1 <= len(documents) <= self.config.max_documents
            or any(type(x) is not str or not x.strip() for x in documents)
        ):
            raise ValueError("Encoder needs a bounded nonempty ordered document tuple")
        if type(query) is not str or not query.strip():
            raise ValueError("Encoder query must be nonempty literal text")
        if (
            len(query.encode()) + sum(len(text.encode()) for text in documents)
            > self.config.max_input_bytes
        ):
            raise ValueError("Encoder input exceeds frozen byte budget")
        import numpy as np

        with self._held(control):
            if self._closed:
                raise OwnershipConflict("Encoder is closed; no automatic retry")
            try:
                if self._model is None:
                    verify_encoder(self.root, self.files, self.config, control)
                    self._model = self._loader(self.root, self.config.cpu_threads)
                    control.checkpoint()
                reused = self._documents == documents and self._vectors is not None
                vectors = (
                    self._vectors
                    if reused
                    else self._model.encode(
                        list(documents),
                        normalize_embeddings=True,
                        batch_size=32,
                        show_progress_bar=False,
                    )
                )
                control.checkpoint()
                self._check(vectors, len(documents))
                assert vectors is not None
                query_vectors = self._model.encode(
                    [query],
                    normalize_embeddings=True,
                    batch_size=32,
                    show_progress_bar=False,
                )
                control.checkpoint()
                self._check(query_vectors, 1)
                scores = vectors @ query_vectors[0]
                if not np.isfinite(scores).all():
                    raise EvidenceIntegrityError("Nonfinite dot product")
                result = EncodedScores(
                    model_files_sha256=self.files.digest,
                    config_sha256=hashlib.sha256(
                        self.config.model_dump_json().encode()
                    ).hexdigest(),
                    documents_sha256=hashlib.sha256(
                        json.dumps(
                            documents, ensure_ascii=False, separators=(",", ":")
                        ).encode()
                    ).hexdigest(),
                    query_sha256=hashlib.sha256(query.encode()).hexdigest(),
                    document_vectors_sha256=hashlib.sha256(
                        vectors.tobytes(order="C")
                    ).hexdigest(),
                    query_vector_sha256=hashlib.sha256(
                        query_vectors.tobytes(order="C")
                    ).hexdigest(),
                    scores=tuple(float(x) for x in scores),
                    documents_reused=reused,
                )
                control.checkpoint()
                self._documents = documents
                self._vectors = vectors.copy()
                self._vectors.flags.writeable = False
                return result
            except BaseException:
                self._model = None
                self._documents = None
                self._vectors = None
                self._closed = True
                raise

    def _check(self, value: "NDArray[np.float32] | None", rows: int) -> None:
        import numpy as np

        if (
            not isinstance(value, np.ndarray)
            or value.dtype != np.float32
            or value.shape != (rows, self.config.dimensions)
            or not np.isfinite(value).all()
            or not np.allclose(np.linalg.norm(value, axis=1), 1.0, rtol=1e-4, atol=1e-4)
        ):
            raise EvidenceIntegrityError(
                "Encoder output must be normalized finite float32 rows"
            )
