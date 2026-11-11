"""Tiny file tree and numeric model double; never substituted for live parity."""

import hashlib
from pathlib import Path
from importlib.metadata import version

import numpy as np
from numpy.typing import NDArray

from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.domain.encoding import (
    EncoderFile,
    EncoderFiles,
    EncoderConfig,
    EncoderPackage,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_run_journal import CancelSwitch, command


def control() -> OperationControl:
    return OperationGuards(SystemClock(), CancelSwitch()).bind(command())


def config() -> EncoderConfig:
    return EncoderConfig(
        packages=tuple(
            EncoderPackage.model_validate(dict(name=name, version=version(name)))
            for name in (
                "numpy",
                "sentence-transformers",
                "tokenizers",
                "torch",
                "transformers",
            )
        ),
        cpu_threads=2,
        max_documents=100,
        max_input_bytes=8 * 1024 * 1024,
    )


def model_files() -> EncoderFiles:
    members = []
    for name in (
        "1_Pooling/config.json",
        "config.json",
        "model.safetensors",
        "modules.json",
        "tokenizer.json",
    ):
        raw = name.encode()
        members.append(
            EncoderFile(
                path=name, sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw)
            )
        )
    return EncoderFiles(files=tuple(members))


def files(root: Path) -> EncoderFiles:
    manifest = model_files()
    for member in manifest.files:
        path = root / member.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(member.path.encode())
    return manifest


class NumericModel:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.bad: str | None = None

    def encode(
        self,
        sentences: list[str],
        *,
        normalize_embeddings: bool,
        batch_size: int,
        show_progress_bar: bool,
    ) -> NDArray[np.float32]:
        assert normalize_embeddings and batch_size == 32 and not show_progress_bar
        self.calls.append(tuple(sentences))
        if self.bad == "raise":
            raise RuntimeError("unit encode failed")
        rows = np.zeros((len(sentences), 384), dtype=np.float32)
        for i, text in enumerate(sentences):
            rows[i, sum(text.encode()) % 384] = 1.0
        if self.bad == "shape":
            return rows[:, :383]
        if self.bad == "zero":
            rows[:] = 0
        if self.bad == "nan":
            rows[0, 0] = np.nan
        if self.bad == "inf":
            rows[0, 0] = np.inf
        return rows


class Loader:
    def __init__(self, model: NumericModel | None = None) -> None:
        self.model = model or NumericModel()
        self.calls = 0

    def __call__(self, root: Path, threads: int) -> NumericModel:
        self.calls += 1
        return self.model
