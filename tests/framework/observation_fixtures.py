"""Synthetic public browser facts; no environment/closure qualification."""

from datetime import datetime, timezone

from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.observation import Observation, BrowserTab


def sample_observation(
    task: TaskIdentity, context_id: str = "context", attempt_id: str = "initial-attempt"
) -> Observation:
    return Observation(
        observation_id="initial-observation",
        task=task,
        context_id=context_id,
        attempt_id=attempt_id,
        sequence=0,
        captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        tabs=(
            BrowserTab(tab_id="main", url="https://map.example/", title="Public map"),
        ),
        active_tab_id="main",
        state="ready",
        text="[1] heading Public map\n[2] searchbox Search",
    )
