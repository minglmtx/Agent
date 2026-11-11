"""The one qualified SFT entry; no raw JSONL or default authority fallback."""

from lab_generate_skill.application.train_sft import TrainingDeps, train_sft
from lab_generate_skill.domain.training import TrainingPlan, TrainingReceipt


def main(
    plan: TrainingPlan | None = None, deps: TrainingDeps | None = None
) -> TrainingReceipt:
    if plan is None or deps is None:
        raise ValueError(
            "SFT requires a frozen TrainingPlan and trusted dataset/phase/runtime dependencies; raw JSONL training entry is retired"
        )
    return train_sft(plan, deps)
