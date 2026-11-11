"""Validated export consumer view; constructing data never grants trainer rights."""

from dataclasses import dataclass
from typing import Literal
from .dataset import DatasetManifest, TrainingExample
from .export import ExportReceipt


@dataclass(frozen=True)
class LoadedDataset:
    receipt: ExportReceipt
    manifest: DatasetManifest | None
    examples: tuple[TrainingExample, ...]
    purpose: Literal["inspect", "sft"]
