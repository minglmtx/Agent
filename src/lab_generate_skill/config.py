from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


def _abspath(path: Path, base: Path) -> Path:
    candidate = path if path.is_absolute() else base / path
    return Path(os.path.abspath(os.fspath(candidate)))


WEB_DOMAINS = ("gitlab", "map", "reddit", "shopping", "shopping_admin")


class PathsSettings(BaseModel):
    project_root: Path = Path("..")
    gobrowse_raw: Path = Path("../../datasets/Go-Browse-WA/raw")
    prepared_dir: Path = Path("../../datasets/Go-Browse-WA/processed")
    qwen_model: Path = Path("../../models/Qwen3-8B")
    prompt_template: Path = Path("prompts/trajectory_to_compact_skill.md")
    trajectories_dir: Path = Path("../../datasets/Go-Browse-WA/processed/trajectories")
    artifacts_dir: Path = Path("../../outputs/gobrowse-skill-bank")
    runtime_output_dir: Path = Path("../../outputs/gobrowse-runtime")

    def anchored(self, config_dir: Path) -> "PathsSettings":
        project_root = _abspath(self.project_root, config_dir)
        values = self.model_dump()
        for name, value in values.items():
            values[name] = (
                project_root
                if name == "project_root"
                else _abspath(value, project_root)
            )
        return PathsSettings.model_validate(values)


class CollectionSettings(BaseModel):
    domains: list[str] = Field(default_factory=lambda: list(WEB_DOMAINS))
    rollouts_per_task: int = Field(default=2, ge=1, le=2)
    base_seed: int = 42
    resume: bool = True

    @model_validator(mode="after")
    def check_domains(self):
        if not self.domains or set(self.domains) - set(WEB_DOMAINS):
            raise ValueError("domains must be a nonempty subset of WEB_DOMAINS")
        return self


class BrowserSettings(BaseModel):
    headless: bool = True
    max_steps: int | None = Field(default=None, ge=1)
    repeating_action_failure_th: int = Field(default=3, ge=1)
    parsing_failure_th: int = Field(default=3, ge=1)
    viewport_width: int = Field(default=1280, ge=320)
    viewport_height: int = Field(default=720, ge=240)


class GenerationSettings(BaseModel):
    backend: Literal["transformers", "openai"] = "transformers"
    model: str = "Qwen3-8B"
    temperature: float = Field(default=0.7, ge=0.0)
    top_p: float = Field(default=0.9, gt=0.0, le=1.0)
    max_new_tokens: int = Field(default=4096, ge=1)
    max_input_tokens: int = Field(default=28672, ge=256)
    enable_thinking: bool = True
    dtype: str = "auto"
    device_map: str = "auto"
    api_base: str | None = None
    api_key_env: str = "OPENAI_API_KEY"
    reasoning_effort: str | None = None
    provider_max_price: dict[str, float] | None = None
    structured_skill: bool = False
    send_sampling_parameters: bool = True


class SkillBuildSettings(BaseModel):
    prompt_version: str = "gobrowse-compact-v1"
    skills_per_trajectory: Literal[1] = 1
    include_failed_trajectories: bool = True
    selection: Literal["all", "outcome_pair", "outcome_balanced"] = "outcome_balanced"
    require_outcome_pair: bool = False
    schema_format: Literal["legacy", "compact"] = "compact"
    max_attempts: int = Field(default=2, ge=1, le=10)

    @model_validator(mode="after")
    def validate_pair_policy(self):
        if (
            self.selection in {"outcome_pair", "outcome_balanced"}
            and not self.include_failed_trajectories
        ):
            raise ValueError(
                "Outcome selection requires include_failed_trajectories=true"
            )
        if self.selection == "outcome_balanced" and self.require_outcome_pair:
            raise ValueError(
                "outcome_balanced permits same-outcome fallback; require_outcome_pair must be false"
            )
        return self


class EmbeddingSettings(BaseModel):
    backend: Literal[
        "local_hidden_state", "sentence_transformers", "openai", "tfidf"
    ] = "local_hidden_state"
    model: str = "Qwen3-8B"
    batch_size: int = Field(default=2, ge=1)
    max_length: int = Field(default=1024, ge=32)
    dtype: str = "auto"
    device_map: str = "auto"
    api_base: str | None = None
    api_key_env: str = "OPENAI_API_KEY"


class ClusteringSettings(BaseModel):
    cosine_similarity_threshold: float = Field(default=0.92, gt=0.0, lt=1.0)
    compare_within_domain: bool = True


class Settings(BaseModel):
    paths: PathsSettings
    browser: BrowserSettings = BrowserSettings()
    collection: CollectionSettings = CollectionSettings()
    # generation is the trainable Qwen3 generator role, reserved for later SFT/RL.
    generation: GenerationSettings = GenerationSettings()
    actor: GenerationSettings = GenerationSettings(
        model="Qwen/Qwen2.5-7B-Instruct",
        enable_thinking=False,
    )
    skill_extractor: GenerationSettings = GenerationSettings(
        backend="openai",
        model="openai/gpt-5.6-luna-pro",
        api_base="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        max_new_tokens=1000,
        reasoning_effort="medium",
        structured_skill=True,
        provider_max_price={"prompt": 0.2, "completion": 1.2},
    )
    skill_build: SkillBuildSettings = SkillBuildSettings()
    embedding: EmbeddingSettings = EmbeddingSettings()
    clustering: ClusteringSettings = ClusteringSettings()

    def generation_model_path_or_name(self) -> str:
        if (
            self.generation.backend == "transformers"
            and self.generation.model == "Qwen3-8B"
        ):
            return os.fspath(self.paths.qwen_model)
        return self.generation.model

    def embedding_model_path_or_name(self) -> str:
        if (
            self.embedding.backend == "local_hidden_state"
            and self.embedding.model == "Qwen3-8B"
        ):
            return os.fspath(self.paths.qwen_model)
        return self.embedding.model


def load_settings(config_path: str | Path) -> Settings:
    path = Path(config_path)
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    settings = Settings.model_validate(raw)
    settings.paths = settings.paths.anchored(path.parent)
    return settings
