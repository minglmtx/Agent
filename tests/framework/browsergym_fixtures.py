"""Explicit loopback-only engineering browser permissions, never production."""

from datetime import datetime, timezone
from typing import Literal
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.evidence import EvidenceRequirements
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.lifecycle import ResourceOwner
from test_core_contracts import identity

CHROMIUM = "/anvme/workspace/r102bf10-lab-generate-skill/assets/runtime-20261025-v1/cache/playwright/chromium-1117/chrome-linux/chrome"


def spec(url: str = "http://127.0.0.1:8000/") -> BrowserSessionSpec:
    task = PublicTask(
        identity=identity(),
        goal="Set the description and save",
        start_url=url,
        allowed_actions=("fill", "click", "send_msg_to_user"),
    )
    scope = StateScope(
        owner=ResourceOwner(
            run_id="run", owner_id="owner", job_id="engineering", worker_id="browser"
        ),
        task=task.identity,
        attempt_id="attempt",
        context_id="browser-context",
    )
    return BrowserSessionSpec(
        scope=scope,
        task=task,
        chromium_executable=CHROMIUM,
        seed=0,
        action_timeout_ms=5000,
        max_events=100,
        requirements=EvidenceRequirements(
            events=("before_action", "after_action", "response", "terminal")
        ),
    )


def operation(value: BrowserSessionSpec, name: str) -> OperationContext:
    from datetime import timedelta

    return OperationContext(
        operation_id=name,
        run_id=value.scope.owner.run_id,
        owner_id=value.scope.owner.owner_id,
        attempt_id=value.scope.attempt_id,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=90),
    )


class LoopbackAuthority:
    denied = False

    def verify(
        self,
        value: BrowserSessionSpec,
        phase: Literal["start", "step", "close"],
        action: BrowserAction | None,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if phase != "close" and (
            self.denied or not value.task.start_url.startswith("http://127.0.0.1:")
        ):
            raise OwnershipConflict(
                "Only this engineering loopback fixture is permitted"
            )
